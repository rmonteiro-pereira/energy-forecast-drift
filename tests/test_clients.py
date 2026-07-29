"""API clients: payload parsing, delta windows, retry policy, secret hygiene.

No network is touched — httpx's MockTransport plays the role of the APIs, which
also lets us prove the retry/backoff behaviour deterministically.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import httpx
import pandas as pd
import pytest

from ingest import eia, http, openmeteo

UTC = UTC


# --------------------------------------------------------------------------
# EIA
# --------------------------------------------------------------------------


def eia_payload(n: int, total: int | None = None) -> dict:
    return {
        "response": {
            "total": str(total if total is not None else n),
            "data": [
                {
                    "period": f"2026-01-{1 + i // 24:02d}T{i % 24:02d}",
                    "respondent": "PJM",
                    "type": "D",
                    "value": 90000 + i,
                    "value-units": "megawatthours",
                }
                for i in range(n)
            ],
        }
    }


def test_eia_payload_becomes_a_tidy_utc_frame(monkeypatch):
    monkeypatch.setenv("EIA_API_KEY", "test-key")
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json=eia_payload(48)))

    with httpx.Client(transport=transport) as client:
        df = eia.fetch_demand(
            client, "PJM", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 3, tzinfo=UTC)
        )

    assert len(df) == 48
    assert str(df["timestamp_utc"].dt.tz) == "UTC"
    assert df["timestamp_utc"].is_monotonic_increasing
    assert df["demand_mwh"].dtype.kind == "f"


def test_eia_rows_with_a_null_value_are_dropped(monkeypatch):
    monkeypatch.setenv("EIA_API_KEY", "test-key")
    payload = eia_payload(3)
    payload["response"]["data"][1]["value"] = None
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json=payload))

    with httpx.Client(transport=transport) as client:
        df = eia.fetch_demand(
            client, "PJM", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)
        )

    assert len(df) == 2


def test_eia_without_a_key_raises_a_pointed_error(monkeypatch):
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    with (
        httpx.Client() as client,
        pytest.raises(eia.MissingApiKey, match=re.escape("docs/BLOCKED.md")),
    ):
        eia.fetch_demand(
            client, "PJM", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)
        )


def test_respondent_is_verified_against_the_api_not_assumed(monkeypatch):
    monkeypatch.setenv("EIA_API_KEY", "test-key")
    facets = {"response": {"facets": [{"id": "PJM", "name": "PJM Interconnection, LLC"}]}}
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json=facets))

    with httpx.Client(transport=transport) as client:
        assert eia.discover_respondent(client, "pjm")["name"].startswith("PJM")
        with pytest.raises(http.ApiError, match="not a valid EIA respondent"):
            eia.discover_respondent(client, "NOT_A_BA")


def test_first_run_backfills_and_later_runs_pull_only_the_delta():
    now = datetime(2026, 7, 1, 12, tzinfo=UTC)

    start, end = eia.default_window(None, 730, timedelta(days=3), now=now)
    assert (end - start).days == 730

    stored = pd.Timestamp("2026-06-30 10:00", tz="UTC")
    start, end = eia.default_window(stored, 730, timedelta(days=3), now=now)
    # Restart before the newest stored hour so upstream revisions overwrite.
    assert start == stored.to_pydatetime() - timedelta(days=3)
    assert end == now


# --------------------------------------------------------------------------
# Open-Meteo
# --------------------------------------------------------------------------


def test_open_meteo_flags_future_hours_as_not_observed():
    now = pd.Timestamp.now(tz="UTC").floor("h")
    times = [(now + pd.Timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in (-2, -1, 5)]
    payload = {"hourly": {"time": times, "temperature_2m": [10.0, 11.0, 12.0]}}

    df = openmeteo._to_frame(payload, "site", "open_meteo_forecast")

    assert list(df["is_observed"]) == [True, True, False]


def test_open_meteo_stitches_archive_and_recent_windows():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        base = pd.Timestamp.now(tz="UTC").floor("h") - pd.Timedelta(days=20)
        times = [(base + pd.Timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(48)]
        return httpx.Response(200, json={"hourly": {"time": times, "temperature_2m": [1.0] * 48}})

    end = datetime.now(UTC)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        df = openmeteo.fetch_weather(client, "site", 40.0, -75.0, end - timedelta(days=30), end)

    assert "archive-api.open-meteo.com" in calls, "archive leg must run for old history"
    assert "api.open-meteo.com" in calls, "recent leg must cover the archive lag"
    assert df["timestamp_utc"].is_monotonic_increasing


# --------------------------------------------------------------------------
# Shared HTTP policy
# --------------------------------------------------------------------------


def test_transient_failures_are_retried_within_the_budget(monkeypatch):
    monkeypatch.setattr(http.time, "sleep", lambda _s: None)
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert http.get_json(client, "https://example.test/x", {}) == {"ok": True}
    assert attempts["n"] == 3


def test_retries_stop_at_three_attempts(monkeypatch):
    monkeypatch.setattr(http.time, "sleep", lambda _s: None)
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(500)

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(http.ApiError),
    ):
        http.get_json(client, "https://example.test/x", {})
    assert attempts["n"] == http.MAX_RETRIES == 3


def test_a_bad_key_is_not_retried(monkeypatch):
    monkeypatch.setattr(http.time, "sleep", lambda _s: None)
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(403)

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(http.ApiError, match="EIA_API_KEY"),
    ):
        http.get_json(client, "https://example.test/x", {})
    assert attempts["n"] == 1, "retrying a rejected key only burns quota"


def test_secrets_never_survive_redaction():
    url = "https://api.eia.gov/v2/x/data/?api_key=SUPERSECRET&frequency=hourly"
    assert "SUPERSECRET" not in http.redact(url)
    assert http.redact_params({"api_key": "SUPERSECRET", "frequency": "hourly"}) == {
        "api_key": "***",
        "frequency": "hourly",
    }
