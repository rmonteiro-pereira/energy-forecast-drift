"""Cost accounting: three lines, never summed, never published unstamped.

The gate here is G7, and its earlier wording was a presence check —
"does the artifact have a `hardware` block?" — which
`{"cpu_model": "", "n_threads": 0, "ram_gb": 0.0, "device": "unknown"}`
satisfies while publishing a comparison with a fabricated stamp. Domain, not
presence.

The second half is the no-totals rule. Summing `fit_cpu_s` into `infer_cpu_s`
hands a zero-shot model a win that belongs to the protocol: the refit is 98.7% of
the GBM's cost and 55 refits is a choice of this harness, not a property of
LightGBM.
"""

from __future__ import annotations

import time

import pytest

from foundation import cost


def _valid_hardware() -> dict:
    return cost.hardware_block(n_threads=1)


def _valid_arm(arm_id: str = "lgbm_17_demand_only") -> dict:
    return {"id": arm_id, "fit_cpu_s": 54.86, "infer_cpu_s": 0.72, "load_cpu_s": 0.0}


def _artifact(**overrides) -> dict:
    artifact = {"hardware": _valid_hardware(), "arms": [_valid_arm()]}
    artifact.update(overrides)
    return artifact


# --------------------------------------------------------------------------
# The hardware stamp comes from the standard library on both platforms.
# --------------------------------------------------------------------------


def test_the_hardware_block_is_measured_not_declared():
    block = cost.hardware_block(n_threads=1)

    assert len(block["cpu_model"].replace(" ", "")) >= 3
    assert block["n_threads"] == 1
    assert block["ram_gb"] > 0
    assert block["device"] == "cpu"


def test_ram_is_readable_offline_without_a_new_dependency():
    """The RFC once made this nullable on a false premise.

    It claimed there was no offline source on the implementer's platform because
    `psutil` is absent from the lockfile and `resource` is Unix-only. Both
    `GlobalMemoryStatusEx` and `os.sysconf` are standard library.
    """
    assert cost._ram_gb() > 0


def test_peak_rss_is_readable_and_grows():
    before = cost.peak_rss_mb()
    ballast = [b"x" * 1024 for _ in range(20_000)]
    after = cost.peak_rss_mb()

    assert before > 0
    assert after >= before
    del ballast


def test_a_thread_count_below_one_is_refused():
    with pytest.raises(cost.CostGateError, match="n_threads must be"):
        cost.hardware_block(n_threads=0)


# --------------------------------------------------------------------------
# The meter keeps the three lines apart.
# --------------------------------------------------------------------------


def test_the_meter_accumulates_each_line_separately():
    meter = cost.CostMeter()

    with meter.timing("fit"):
        _burn_cpu(0.05)
    with meter.timing("infer"):
        _burn_cpu(0.01)

    assert meter.fit_cpu_s > meter.infer_cpu_s > 0
    assert meter.load_cpu_s == 0.0


def test_the_block_has_no_total():
    meter = cost.CostMeter()
    with meter.timing("fit"):
        _burn_cpu(0.01)

    block = meter.block(n_predictions=1320)

    assert set(cost.LINES) <= set(block)
    for forbidden in cost.FORBIDDEN_TOTALS:
        assert forbidden not in block
    assert block["n_predictions"] == 1320


def test_the_meter_refuses_an_unknown_line():
    meter = cost.CostMeter()
    with pytest.raises(ValueError, match="unknown cost line"), meter.timing("wall"):
        pass


def test_a_block_with_no_predictions_is_refused():
    with pytest.raises(cost.CostGateError, match="n_predictions must be"):
        cost.CostMeter().block(n_predictions=0)


# --------------------------------------------------------------------------
# G7. Canary first, negative control always.
# --------------------------------------------------------------------------


def test_g7_accepts_a_properly_stamped_artifact():
    """Negative control. A gate that fires on the honest case is not a gate."""
    cost.assert_cost_provenance(_artifact())


def test_g7_refuses_a_placeholder_hardware_block():
    """The canary the presence check was green on."""
    placeholder = {"cpu_model": "", "n_threads": 0, "ram_gb": 0.0, "device": "unknown"}

    with pytest.raises(cost.CostGateError) as excinfo:
        cost.assert_cost_provenance(_artifact(hardware=placeholder))

    assert excinfo.value.gate == "cost-provenance"
    message = str(excinfo.value)
    for field_name in ("cpu_model", "n_threads", "ram_gb", "device"):
        assert field_name in message, "the refusal must name every field it rejected"


@pytest.mark.parametrize(
    "key, value",
    [
        ("cpu_model", "  "),
        ("n_threads", 0),
        ("ram_gb", 0),
        ("device", "tpu"),
    ],
)
def test_g7_refuses_each_hardware_field_on_its_own(key, value):
    hardware = {**_valid_hardware(), key: value}

    with pytest.raises(cost.CostGateError, match="placeholder"):
        cost.assert_cost_provenance(_artifact(hardware=hardware))


def test_g7_refuses_an_arm_missing_a_cost_line():
    arm = _valid_arm()
    del arm["load_cpu_s"]

    with pytest.raises(cost.CostGateError, match="missing cost line"):
        cost.assert_cost_provenance(_artifact(arms=[arm]))


def test_g7_refuses_an_artifact_with_no_arms():
    """Anti-vacuum. An empty list satisfies every per-arm check ever written."""
    with pytest.raises(cost.CostGateError, match="vacuously"):
        cost.assert_cost_provenance(_artifact(arms=[]))


@pytest.mark.parametrize("name", cost.FORBIDDEN_TOTALS)
def test_g7_refuses_a_total_by_name(name):
    arm = {**_valid_arm(), name: 55.58}

    with pytest.raises(cost.CostGateError, match="never summed"):
        cost.assert_cost_provenance(_artifact(arms=[arm]))


def test_g7_refuses_a_total_hiding_under_a_harmless_name():
    """The interesting version: a field that reads innocently and holds fit+infer.

    A name-only check passes this, and the reader has no way to know the number
    they are quoting is the sum that the whole cost contract forbids.
    """
    arm = _valid_arm()
    arm["elapsed"] = arm["fit_cpu_s"] + arm["infer_cpu_s"]

    with pytest.raises(cost.CostGateError, match="equals fit\\+infer"):
        cost.assert_cost_provenance(_artifact(arms=[arm]))


def test_g7_does_not_cry_wolf_when_a_line_is_zero():
    """A zero-shot arm has `fit_cpu_s == 0.0`, so some sums equal a single line.

    Rejecting that would make the gate unusable on exactly the arm the lane
    exists to measure.
    """
    arm = {"id": "chronos_bolt@ctx671", "fit_cpu_s": 0.0, "infer_cpu_s": 12.5, "load_cpu_s": 3.1}

    cost.assert_cost_provenance(_artifact(arms=[arm]))


def test_the_zero_shot_fit_line_is_measured_not_stipulated():
    """`fit_cpu_s == 0.0` has to come from a meter that was never asked to fit."""
    meter = cost.CostMeter()
    with meter.timing("infer"):
        _burn_cpu(0.01)
    with meter.timing("load"):
        _burn_cpu(0.01)

    block = meter.block(n_predictions=24)

    assert block["fit_cpu_s"] == 0.0
    assert block["infer_cpu_s"] > 0
    assert block["load_cpu_s"] > 0


def _burn_cpu(seconds: float) -> None:
    end = time.process_time() + seconds
    while time.process_time() < end:
        pass
