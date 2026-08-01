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
# Archived forecasts — what was predicted, never what happened
# --------------------------------------------------------------------------


def forecast_payload(times: list[str], suffix: str = "") -> dict:
    hourly: dict[str, list] = {"time": times}
    for name in openmeteo.FORECAST_VARIABLES:
        hourly[f"{name}{suffix}"] = [1.0] * len(times)
    return {"hourly": hourly}


def two_leg_handler(
    archived: dict,
    current: dict,
    seen: dict | None = None,
):
    def handler(request: httpx.Request) -> httpx.Response:
        if "historical-forecast" in request.url.host:
            if seen is not None:
                seen["hourly"] = request.url.params["hourly"]
            return httpx.Response(200, json=archived)
        if seen is not None:
            seen["current_params"] = dict(request.url.params)
        return httpx.Response(200, json=current)

    return handler


def test_the_archived_leg_asks_for_the_day_before_run_on_every_variable():
    """Drop the suffix and the endpoint answers with its most recent run.

    That run is initialised *after* the hour it describes, so it is very nearly
    the observation — a near-perfect forecast that would inflate every score in
    the repository while looking completely normal. Nothing else in the stack
    can catch it, because the values arrive well-formed and plausible. So the
    request itself is pinned here.
    """
    seen: dict = {}
    handler = two_leg_handler(
        archived=forecast_payload(["2026-06-01T00:00"], openmeteo.PREVIOUS_DAY_SUFFIX),
        current=forecast_payload([]),
        seen=seen,
    )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        openmeteo.fetch_weather_forecast(
            client,
            "philadelphia_pa",
            39.95,
            -75.16,
            datetime(2026, 6, 1, tzinfo=UTC),
            datetime(2026, 6, 2, tzinfo=UTC),
            now=datetime(2026, 6, 10, tzinfo=UTC),
        )

    requested = seen["hourly"].split(",")
    assert requested, "the archived leg asked for no variables at all"
    assert len(requested) == len(openmeteo.FORECAST_VARIABLES)
    for name in requested:
        assert name.endswith(openmeteo.PREVIOUS_DAY_SUFFIX), f"{name} is not the day-before run"


def test_the_live_run_contributes_only_hours_that_have_not_happened_yet():
    """A past hour must never be stored from the current run.

    The live run's value for an hour that already passed is near-analysis, not
    a day-ahead call. Letting it into the history would make the training
    feature better than anything production could reproduce at serving time.
    """
    now = datetime(2026, 6, 5, 12, tzinfo=UTC)
    handler = two_leg_handler(
        archived=forecast_payload([], openmeteo.PREVIOUS_DAY_SUFFIX),
        current=forecast_payload(["2026-06-05T06:00", "2026-06-05T18:00", "2026-06-06T06:00"]),
    )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        df = openmeteo.fetch_weather_forecast(
            client,
            "philadelphia_pa",
            39.95,
            -75.16,
            datetime(2026, 6, 5, tzinfo=UTC),
            datetime(2026, 6, 6, tzinfo=UTC),
            now=now,
        )

    assert len(df) == 2, "the hour before `now` should have been dropped"
    assert (df["timestamp_utc"] > pd.Timestamp(now)).all()
    assert set(df["lead"]) == {openmeteo.LEAD_CURRENT_RUN}


def test_the_archived_day_before_value_wins_wherever_both_legs_reach():
    """Order matters: `write_incremental` keeps the last row for a key.

    The two legs are disjoint by construction today, but the ordering is what
    keeps stored history consistent with what training consumes if that ever
    changes.
    """
    hour = ["2026-06-01T00:00"]
    handler = two_leg_handler(
        archived=forecast_payload(hour, openmeteo.PREVIOUS_DAY_SUFFIX),
        current=forecast_payload(hour),
    )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        df = openmeteo.fetch_weather_forecast(
            client,
            "philadelphia_pa",
            39.95,
            -75.16,
            datetime(2026, 6, 1, tzinfo=UTC),
            datetime(2026, 6, 2, tzinfo=UTC),
            now=datetime(2026, 6, 10, tzinfo=UTC),
        )

    duplicated = df[df["timestamp_utc"] == pd.Timestamp("2026-06-01T00:00", tz="UTC")]
    assert duplicated["lead"].iloc[-1] == openmeteo.LEAD_PREVIOUS_DAY


def test_a_forecast_row_is_labelled_with_the_lead_it_came_from():
    """`lead` is what lets anyone reading the lake tell the two apart later."""
    assert "lead" in openmeteo.FORECAST_COLUMNS
    assert "is_observed" not in openmeteo.FORECAST_COLUMNS

    frame = openmeteo._to_forecast_frame(
        forecast_payload(["2026-06-01T00:00"], openmeteo.PREVIOUS_DAY_SUFFIX),
        "philadelphia_pa",
        source="open_meteo_historical_forecast",
        lead=openmeteo.LEAD_PREVIOUS_DAY,
        suffix=openmeteo.PREVIOUS_DAY_SUFFIX,
    )

    assert list(frame.columns) == openmeteo.FORECAST_COLUMNS
    assert frame["lead"].iloc[0] == openmeteo.LEAD_PREVIOUS_DAY
    assert frame["temperature_c"].notna().all()


def test_a_variable_the_endpoint_did_not_return_becomes_nan_not_a_crash():
    """Open-Meteo drops variables it has no data for; the schema must hold."""
    payload = forecast_payload(["2026-06-01T00:00"], openmeteo.PREVIOUS_DAY_SUFFIX)
    del payload["hourly"][f"cloud_cover{openmeteo.PREVIOUS_DAY_SUFFIX}"]

    frame = openmeteo._to_forecast_frame(
        payload,
        "philadelphia_pa",
        source="open_meteo_historical_forecast",
        lead=openmeteo.LEAD_PREVIOUS_DAY,
        suffix=openmeteo.PREVIOUS_DAY_SUFFIX,
    )

    assert list(frame.columns) == openmeteo.FORECAST_COLUMNS
    assert frame["cloud_pct"].isna().all()


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


def test_a_200_with_a_non_json_body_becomes_an_ApiError(monkeypatch):
    """An HTML error page behind a proxy still arrives as HTTP 200.

    Without the guard this raised a bare `ValueError` out of `.json()`, which
    escapes the retry loop and bypasses every per-source `except ApiError`.
    """
    monkeypatch.setattr(http.time, "sleep", lambda _s: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body>502 Bad Gateway</body></html>")

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(http.ApiError, match=r"not.*JSON"),
    ):
        http.get_json(client, "https://example.test/x", {})


def test_a_200_with_a_json_array_becomes_an_ApiError(monkeypatch):
    """Valid JSON, wrong shape. Callers index the body, so a list cannot work."""
    monkeypatch.setattr(http.time, "sleep", lambda _s: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[1, 2, 3])

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(http.ApiError, match="not an object but a list"),
    ):
        http.get_json(client, "https://example.test/x", {})


def test_a_200_with_a_json_object_is_returned_unchanged():
    """The guard must not reject the normal case."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": {"data": []}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert http.get_json(client, "https://example.test/x", {}) == {"response": {"data": []}}


def test_a_malformed_body_error_still_redacts_the_key(monkeypatch):
    """The new error message embeds the URL — it must go through redact()."""
    monkeypatch.setattr(http.time, "sleep", lambda _s: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        try:
            http.get_json(client, "https://api.eia.gov/v2/x", {"api_key": "SUPERSECRET"})
        except http.ApiError as exc:
            assert "SUPERSECRET" not in str(exc)
        else:  # pragma: no cover
            pytest.fail("expected ApiError")


def test_secrets_never_survive_redaction():
    url = "https://api.eia.gov/v2/x/data/?api_key=SUPERSECRET&frequency=hourly"
    assert "SUPERSECRET" not in http.redact(url)
    assert http.redact_params({"api_key": "SUPERSECRET", "frequency": "hourly"}) == {
        "api_key": "***",
        "frequency": "hourly",
    }
