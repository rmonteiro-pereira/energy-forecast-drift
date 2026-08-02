"""The daily entrypoint, end to end, plus the two things it must never do.

The exit criterion for M5 is "the daily entrypoint runs end-to-end and refreshes
the metrics files", so that is asserted literally: run it into a temp directory
and check every artifact it claims to write is there and well formed.

The two must-nevers get their own tests because both are silent failures:

* publishing fixture numbers from a cron as if they were data — prevented by
  `--require-eia-key`, which the workflow passes;
* scoring the monitoring windows with a model that was trained on them, which
  makes the reference error artificially small and every later window look
  degraded forever.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from models import tracking
from pipeline import daily

# Ingestion is skipped (it would hit the network) and the booster is small; the
# pipeline's wiring is what is under test, not LightGBM's accuracy.
#
# `--no-champion` is not decoration. The monitoring windows are anchored on the
# champion's `train_data_end_utc`, so without it these tests read whatever
# happens to be in the developer's local `mlflow.db` — and a champion trained up
# to the end of the fixture legitimately produces no post-training data at all,
# which changes the artifacts these assertions describe. That made the suite
# pass or fail on untracked local state. Pinned here so the full-artifact path
# is exercised deterministically; the anchored path has its own test below.
FAST = [
    "--source",
    "synthetic",
    "--skip-ingest",
    "--no-evidently",
    "--no-champion",
    "--train-stride-hours",
    "12",
    "--num-boost-round",
    "60",
]

EXPECTED_ARTIFACTS = {
    "forecast.json",
    "monitor.json",
    "drift.json",
    "drift_summary.md",
    "pipeline.json",
    "forecast_vs_actual.png",
    "rolling_mae.png",
}


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("daily")
    assert daily.main([*FAST, "--out-dir", str(out)]) == 0
    return out


def _load(run_dir, name: str) -> dict:
    return json.loads((run_dir / name).read_text(encoding="utf-8"))


def test_the_run_writes_every_artifact_it_promises(run_dir):
    record = _load(run_dir, "pipeline.json")
    assert record["status"] == "ok"
    assert set(record["artifacts"]) == EXPECTED_ARTIFACTS
    for name in EXPECTED_ARTIFACTS:
        assert (run_dir / name).exists(), f"{name} is listed in the run record but missing"
        assert (run_dir / name).stat().st_size > 0


def test_the_stages_run_in_the_documented_order(run_dir):
    record = _load(run_dir, "pipeline.json")
    assert [s["step"] for s in record["steps"]] == [
        "ingest",
        "features",
        "score",
        "forecast",
        "monitor",
        "drift",
    ]
    assert all(s["status"] in {"ok", "skipped", "degraded"} for s in record["steps"])


def test_the_pngs_are_real_images_and_small_enough_to_commit(run_dir):
    for name in ("forecast_vs_actual.png", "rolling_mae.png"):
        path = run_dir / name
        assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", f"{name} is not a PNG"
        assert path.stat().st_size < 5_000_000, f"{name} is too big for metrics/"


def test_forecast_json_separates_scored_history_from_the_live_forecast(run_dir):
    payload = _load(run_dir, "forecast.json")
    assert payload["history"], "no scored history"
    assert payload["forward"], "no forward forecast"

    # History has actuals; the forward forecast cannot, and must not invent them.
    assert all("actual_mwh" in row for row in payload["history"])
    assert all("actual_mwh" not in row for row in payload["forward"])

    last_history = pd.Timestamp(payload["history"][-1]["target_utc"])
    first_forward = pd.Timestamp(payload["forward"][0]["target_utc"])
    assert first_forward > last_history


def test_monitor_json_carries_the_rolling_series_and_the_alert_line(run_dir):
    payload = _load(run_dir, "monitor.json")
    assert payload["daily"], "the rolling MAE series is empty"
    assert {"day_utc", "mae", "mae_rolling", "window"} <= set(payload["daily"][0])
    assert payload["alert_line_mae"] > payload["reference"]["mae"]
    assert payload["severity"] in {"ok", "warn", "alert"}


def test_the_monitor_and_the_drift_verdict_cannot_disagree(run_dir):
    """Both read the same performance section, so their severities must match."""
    monitor = _load(run_dir, "monitor.json")
    drift = _load(run_dir, "drift.json")
    assert monitor["severity"] == drift["drift"]["performance"]["severity"]
    assert monitor["mae_degradation"] == drift["drift"]["performance"]["mae_degradation"]


def test_drift_json_still_has_four_sections_and_a_verdict(run_dir):
    drift = _load(run_dir, "drift.json")
    assert set(drift["drift"]) == {"feature", "target", "prediction", "performance"}
    assert isinstance(drift["verdict"]["should_retrain"], bool)


def test_every_artifact_carries_the_same_honesty_flag(run_dir):
    for name in ("forecast.json", "monitor.json", "drift.json", "pipeline.json"):
        payload = _load(run_dir, name)
        assert payload["is_real"] is False, f"{name} lost the is_real flag"
        assert "SYNTHETIC" in payload["warning"], f"{name} lost the synthetic warning"


# ---------------------------------------------------------------------------
# must-never #1: a cron publishing fixture numbers as data
# ---------------------------------------------------------------------------
def test_require_eia_key_fails_fast_with_instructions(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    code = daily.main([*FAST, "--out-dir", str(tmp_path), "--require-eia-key"])

    assert code == 2
    assert not list(tmp_path.iterdir()), "nothing may be written before the key check"

    message = capsys.readouterr().err
    assert "EIA_API_KEY is not set" in message
    assert "docs/BLOCKED.md" in message
    assert "register" in message


def test_without_the_flag_it_degrades_to_the_fixture_instead(run_dir):
    """The local path must stay runnable — that is what keeps the repo testable."""
    record = _load(run_dir, "pipeline.json")
    features = next(s for s in record["steps"] if s["step"] == "features")
    assert features["status"] == "degraded"
    assert features["kind"] == "synthetic_fixture"


# ---------------------------------------------------------------------------
# must-never #2: scoring a monitoring window in sample
# ---------------------------------------------------------------------------
def _pipeline(tmp_path, **overrides):
    args = daily._parse_args([*FAST, "--out-dir", str(tmp_path)])
    for key, value in overrides.items():
        setattr(args, key, value)
    return daily.DailyPipeline(args)


def test_a_champion_whose_training_span_covers_the_window_is_not_used(tmp_path):
    pipeline = _pipeline(tmp_path)
    pipeline.champion = object()
    pipeline.model_info = {"version": "7", "train_data_end_utc": "2026-07-28T00:00:00+00:00"}

    booster, info = pipeline._monitoring_booster(pd.Timestamp("2026-06-16T00:00:00+00:00"))
    assert booster is None, "an in-sample champion must not score the monitoring windows"
    assert info["source"] == "fitted_on_train_window"
    assert "in-sample" in info["reason"]


def test_a_champion_trained_before_the_window_is_used(tmp_path):
    pipeline = _pipeline(tmp_path)
    sentinel = object()
    pipeline.champion = sentinel
    pipeline.model_info = {"version": "7", "train_data_end_utc": "2026-06-01T00:00:00+00:00"}

    booster, info = pipeline._monitoring_booster(pd.Timestamp("2026-06-16T00:00:00+00:00"))
    assert booster is sentinel
    assert info["source"] == "mlflow_registry"


def test_an_untagged_champion_counts_as_ineligible(tmp_path):
    """Unknown is not safe: a version registered before the tag existed is refused."""
    pipeline = _pipeline(tmp_path)
    pipeline.champion = object()
    pipeline.model_info = {"version": "1", "train_data_end_utc": None}

    booster, info = pipeline._monitoring_booster(pd.Timestamp("2026-06-16T00:00:00+00:00"))
    assert booster is None
    assert "train_data_end_utc" in info["reason"]


def test_no_champion_at_all_falls_back_and_says_why(tmp_path):
    pipeline = _pipeline(tmp_path)
    pipeline.model_info = {"source": "none", "reason": "registry is empty"}

    booster, info = pipeline._monitoring_booster(pd.Timestamp("2026-06-16T00:00:00+00:00"))
    assert booster is None
    assert info["reason"] == "registry is empty"


def test_a_missing_registry_does_not_stop_the_run(tmp_path, monkeypatch):
    """A fresh clone has no mlflow.db; the pipeline must still produce metrics."""

    def unavailable(*_args, **_kwargs):
        raise tracking.ChampionUnavailable("no mlflow.db here")

    monkeypatch.setattr(tracking, "load_champion", unavailable)
    assert daily.main([*FAST, "--out-dir", str(tmp_path)]) == 0

    record = json.loads((tmp_path / "pipeline.json").read_text(encoding="utf-8"))
    assert record["status"] == "ok"
    assert record["served_model"]["source"] == "none"
    assert record["monitoring_model"]["source"] == "fitted_on_train_window"


# ---------------------------------------------------------------------------
# provenance
# ---------------------------------------------------------------------------
def test_a_fixture_trained_champion_keeps_a_real_panel_synthetic(tmp_path):
    pipeline = _pipeline(tmp_path)
    pipeline.provenance = {"is_real": True, "kind": "eia_api_v2"}
    pipeline.champion = object()
    pipeline.model_info = {"trained_on_real_data": False}
    assert pipeline.is_real is False

    pipeline.model_info = {"trained_on_real_data": True}
    assert pipeline.is_real is True


def test_with_no_champion_the_panel_decides_alone(tmp_path):
    pipeline = _pipeline(tmp_path)
    pipeline.provenance = {"is_real": True, "kind": "eia_api_v2"}
    pipeline.champion = None
    assert pipeline.is_real is True


# ---------------------------------------------------------------------------
# the two CLIs that name ingestion legs
# ---------------------------------------------------------------------------
def test_the_daily_job_can_ask_for_every_leg_ingestion_offers():
    """A leg the daily job cannot name is a leg the cron can never pull alone.

    `pipeline.daily` forwards `--ingest-source` verbatim to `python -m ingest`.
    When the archived-forecast leg was added, the two argument lists were
    separate literals — so ingestion grew a leg and the daily job silently could
    not select it. Both now read the same tuple; this asserts they still do.
    """
    from ingest.__main__ import _parse_args as ingest_parse
    from ingest.config import INGEST_LEGS

    assert "weather_forecast" in INGEST_LEGS

    for leg in INGEST_LEGS:
        assert ingest_parse(["--source", leg]).source == leg
        assert daily._parse_args(["--ingest-source", leg]).ingest_source == leg

    with pytest.raises(SystemExit):
        daily._parse_args(["--ingest-source", "not_a_leg"])
