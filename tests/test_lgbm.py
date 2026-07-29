"""LightGBM under the *existing* walk-forward protocol — same folds, no leakage."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from features import panel as panel_mod
from models import backtest, baseline, fixtures, lgbm, tracking, train


@pytest.fixture(scope="module")
def panel() -> pd.DataFrame:
    frame = fixtures.synthetic_series(days=90)
    return panel_mod.build_panel(frame["demand_mwh"], frame["temperature_c"])


@pytest.fixture(scope="module")
def scored(panel) -> tuple[lgbm.WalkForwardLightGBM, backtest.BacktestResult]:
    model = lgbm.WalkForwardLightGBM(panel=panel, train_stride_hours=12, num_boost_round=80)
    result = backtest.run(panel[panel_mod.DEMAND_COLUMN], model, weeks=1)
    return model, result


def test_it_plugs_into_the_existing_protocol_unchanged(scored):
    model, result = scored

    assert list(result.by_horizon["horizon_h"]) == list(range(1, 25))
    assert set(result.by_horizon["n"]) == {len(result.folds)}
    assert model.fits == len(result.folds), "one refit per fold cutoff"


def test_the_model_never_trains_on_a_label_at_or_after_the_cutoff(panel):
    """Spy on every training slice the model builds, fold by fold."""
    model = lgbm.WalkForwardLightGBM(panel=panel, train_stride_hours=24, num_boost_round=20)
    seen: list[tuple[pd.Timestamp, pd.Timestamp]] = []

    original = model.training_slice

    def spy(cutoff):
        train_rows = original(cutoff)
        seen.append((train_rows["target_utc"].max(), cutoff))
        return train_rows

    model.training_slice = spy
    backtest.run(panel[panel_mod.DEMAND_COLUMN], model, weeks=1)

    assert seen, "the model was never asked to train"
    assert all(last_label < cutoff for last_label, cutoff in seen)


def test_a_history_that_reaches_the_cutoff_is_rejected(panel):
    model = lgbm.WalkForwardLightGBM(panel=panel, train_stride_hours=24, num_boost_round=20)
    cutoff = panel.index[-48]
    history = panel[panel_mod.DEMAND_COLUMN].loc[:cutoff]  # inclusive -> illegal

    with pytest.raises(baseline.TemporalLeakageError):
        model(history, pd.DatetimeIndex([cutoff + pd.Timedelta(hours=1)]), cutoff)


def test_future_values_cannot_change_the_metrics(panel):
    """Poison everything after the last scored hour; the numbers must not move."""
    model_a = lgbm.WalkForwardLightGBM(panel=panel, train_stride_hours=24, num_boost_round=40)
    result_a = backtest.run(panel[panel_mod.DEMAND_COLUMN], model_a, weeks=1)

    last_target = result_a.predictions["target_utc"].max()
    poisoned = panel.copy()
    poisoned.loc[poisoned.index > last_target, ["demand_mwh", "temperature_c"]] = 1e9

    model_b = lgbm.WalkForwardLightGBM(panel=poisoned, train_stride_hours=24, num_boost_round=40)
    result_b = backtest.run(poisoned[panel_mod.DEMAND_COLUMN], model_b, weeks=1)

    assert result_a.overall["mae"] == pytest.approx(result_b.overall["mae"])


def test_a_prediction_comes_back_for_every_requested_target(scored):
    _, result = scored

    assert result.predictions["prediction"].notna().all()
    assert len(result.predictions) == len(result.folds) * 24


def test_it_beats_the_seasonal_naive_baseline_on_identical_folds(panel, scored):
    """Head-to-head on the fixture. The *delta* is what M2 has to justify.

    (The fixture is not data, so this asserts the model is doing something real,
    not that any particular MAE is a benchmark.)
    """
    _, model_result = scored
    base = backtest.run(panel[panel_mod.DEMAND_COLUMN], baseline.predict, weeks=1)

    assert base.folds == model_result.folds
    assert model_result.overall["mae"] < base.overall["mae"]


def test_importance_is_ranked_and_normalised(scored):
    model, _ = scored
    ranked = lgbm.importance(model.last_booster, top=5)

    assert len(ranked) == 5
    assert [r["gain_pct"] for r in ranked] == sorted((r["gain_pct"] for r in ranked), reverse=True)
    assert 0.0 < sum(r["gain_pct"] for r in ranked) <= 100.0


def test_the_comparison_block_reports_a_per_horizon_delta(panel, scored):
    _, model_result = scored
    base = backtest.run(panel[panel_mod.DEMAND_COLUMN], baseline.predict, weeks=1)

    comparison = train.compare(base, model_result)

    assert comparison["horizons_total"] == 24
    assert len(comparison["by_horizon"]) == 24
    assert comparison["mae_delta"] < 0
    assert comparison["by_horizon"][0]["baseline_mae"] > 0


def test_the_entrypoint_writes_an_artifact_flagged_not_real(tmp_path):
    exit_code = train.main(
        [
            "--source",
            "synthetic",
            "--fixture-days",
            "90",
            "--weeks",
            "1",
            "--train-stride-hours",
            "24",
            "--num-boost-round",
            "40",
            "--no-mlflow",
            "--out-dir",
            str(tmp_path),
        ]
    )
    artifact = json.loads((tmp_path / "model.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    assert artifact["is_real"] is False
    assert artifact["data"]["is_real"] is False
    assert "SYNTHETIC" in artifact["warning"]
    assert artifact["metrics"]["comparison"]["horizons_total"] == 24
    assert "SYNTHETIC" in (tmp_path / "model_table.md").read_text(encoding="utf-8")


# --- MLflow wiring -------------------------------------------------------
# The tracking round-trip is exercised end to end by the CI smoke step
# (`python -m models.train --weeks 2`), not here: creating the sqlite schema
# runs alembic migrations and costs ~40s, which does not belong in a unit suite.


def test_the_sqlite_uri_is_posix_slashed_so_it_works_on_windows(tmp_path):
    uri = tracking.sqlite_uri(tmp_path / "mlflow.db")

    assert uri.startswith("sqlite:///")
    assert "\\" not in uri


def test_serving_resolves_the_champion_by_alias_not_by_path():
    assert tracking.champion_uri() == "models:/energy-demand-forecaster@champion"
    assert tracking.champion_uri(tracking.CHALLENGER_ALIAS).endswith("@challenger")


def test_mlflow_run_state_is_gitignored():
    """`mlruns/` and the sqlite backend must never reach a commit."""
    from ingest.config import REPO_ROOT

    ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert "mlruns/" in ignored
    assert "*.db" in ignored
    assert tracking.MLFLOW_DB.name.endswith(".db")
