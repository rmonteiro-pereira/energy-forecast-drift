"""The lane artifact's schema, and the fixture that keeps its gates falsifiable.

`metrics/foundation.json` does not exist until the dispatch run, which needs a
key, a lake and a network. Every schema gate aimed at it would therefore be
**vacuously green** for the whole implementable part of this lane — the glob
finds nothing, the assertions hold over an empty set, and the first time anyone
learns whether the gates work is the day the real artifact lands.

`tests/fixtures/foundation.sample.json` is the permanent subject. It is produced
by the same `foundation.compare.build_artifact` that will write the real one, so
a schema change breaks it too.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from foundation import compare, cost

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "foundation.sample.json"
SIZE_CEILING = 5_242_880


@pytest.fixture(scope="module")
def sample() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_the_fixture_exists_and_is_not_empty():
    """Anti-vacuum, in the pattern of `tests/test_artifacts.py:53`.

    Without this, every assertion below is true of a deleted file.
    """
    assert FIXTURE.exists(), "the schema gates have no subject and would pass vacuously"
    assert FIXTURE.stat().st_size > 0


def test_the_fixture_is_far_below_the_size_ceiling(sample):
    assert FIXTURE.stat().st_size < SIZE_CEILING


def test_the_artifact_answers_is_real_in_both_places(sample):
    """`data.is_real` mirrors the top-level flag, and that is not redundancy.

    `tests/test_artifacts.py:81-83` *skips* an artifact whose `data` block has no
    `is_real`, and the CI half reads `kind` only from `data.kind`. An artifact of
    a new shape can therefore slip past both halves of the honesty gate — two
    committed artifacts already do.
    """
    assert "is_real" in sample
    assert isinstance(sample["data"], dict)
    assert sample["data"]["kind"] in {"eia_api_v2", "synthetic_fixture"}
    assert sample["data"]["is_real"] == sample["is_real"]


def test_a_synthetic_artifact_carries_a_real_warning(sample):
    if sample["is_real"]:
        pytest.skip("this fixture describes real data")
    warning = sample["warning"] or ""
    assert "SYNTHETIC" in warning.upper()
    assert "NOT a benchmark" in warning


def test_failed_gate_is_null_or_a_declared_gate(sample):
    assert sample["failed_gate"] is None or sample["failed_gate"] in compare.GATES


def test_every_arm_carries_the_three_cost_lines_and_no_total(sample):
    cost.assert_cost_provenance(sample)
    for arm in sample["arms"]:
        for line in cost.LINES:
            assert isinstance(arm[line], int | float)


def test_every_arm_reports_the_same_n(sample):
    assert len({arm["n"] for arm in sample["arms"]}) == 1


def test_both_ways_of_losing_a_fold_are_reported_separately(sample):
    for arm in sample["arms"]:
        assert isinstance(arm["unscorable_by_own_failure"], int)
        assert isinstance(arm["folds_dropped_vs_intersection"], list)


def test_the_zero_shot_arm_declares_no_in_domain_training(sample):
    zero_shot = [a for a in sample["arms"] if a["refits"] == 0]
    assert zero_shot, "the fixture has no zero-shot arm, so the contrast is untested"
    for arm in zero_shot:
        assert arm["in_domain_training_hours"] == 0
        assert arm["fit_cpu_s"] == 0.0


def test_the_interval_is_blocked_on_origins(sample):
    assert sample["uncertainty"], "no interval: G10 would pass vacuously"
    for report in sample["uncertainty"].values():
        assert report["block"] == "cutoff_utc"
        assert report["n_blocks"] == len(sample["folds_intersected"])
        low, high = report["mae_ratio"]["ci95"]
        assert low <= report["mae_ratio"]["point"] <= high


def test_a_refusal_is_stamped_not_raised():
    """A gate that raises past the caller loses the reason into a traceback."""
    artifact = compare.build_artifact(
        {}, cutoff_candidates=[], contiguity={}, is_real=False, data_kind="synthetic_fixture"
    )

    assert artifact["failed_gate"] == "fold-identity"
    assert artifact["arms"] == []
    assert artifact["data"]["is_real"] is False


def test_a_refusal_cannot_invent_a_gate_name():
    with pytest.raises(ValueError, match="not one of the declared gates"):
        compare._refusal("typo-gate", "boom", False, "synthetic_fixture", None)


def test_metrics_foundation_json_is_real_or_absent():
    """The offline agent must not commit this file.

    Stated as a gate rather than as a prohibition: the RFC's first wording was
    "the agent cannot commit it", which nothing checks. Nothing in the repository
    names `metrics/foundation.json`, so an artifact stamped `is_real: false` would
    land there and only the README banner would notice — and the banner can be
    edited to make itself green.
    """
    published = REPO / "metrics" / "foundation.json"
    if not published.exists():
        return
    payload = json.loads(published.read_text(encoding="utf-8"))
    assert payload["is_real"] is True, "a fixture-derived lane artifact was published"
    assert payload["data"]["kind"] == "eia_api_v2"
