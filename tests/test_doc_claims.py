"""Live counts in prose must match the thing they count.

The failure mode is specific and this repository has had it twice: prose quotes
a number, the number's source moves, the prose keeps saying the old one.
`docs/REPRODUCE.md`'s pointer note quoted "the suite is 208 collected" long
after the suite reached 252, and `docs/MUTATION-TESTING.md` carried a stale
survivor table next to a fresh header. Transcripts are exempt — they are dated
records of what a run printed — but prose stating the *current* count is a live
claim, and a live claim gets a test.

The README and CONTRIBUTING state the Python test count in four places. This
collects the suite and compares, so adding a test without touching the prose
fails here, with both values, instead of silently going stale.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from features import build

REPO = Path(__file__).resolve().parents[1]


def test_the_documented_python_test_count_is_the_collected_one():
    # not `-q`: this pytest's quiet collect prints per-file counts with no total
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-p", "no:cacheprovider"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=REPO,
    ).stdout
    match = re.search(r"(\d+) tests? collected", out)
    assert match, f"could not read a collected count from pytest:\n{out[-500:]}"
    collected = int(match.group(1))

    for name in ("README.md", "CONTRIBUTING.md"):
        text = (REPO / name).read_text(encoding="utf-8")
        claims = re.findall(r"(\d{3}) (?:Python )?tests", text)
        assert claims, f"{name} no longer states the Python test count"
        for claim in claims:
            assert int(claim) == collected, (
                f"{name} claims {claim} tests; pytest collects {collected}"
            )


def _live_prose(path: Path) -> str:
    """The file with its `<details>` blocks removed.

    Collapsed blocks in the README are dated records of the fixture era, labelled
    as history. Prose stating the *current* protocol is a live claim; a
    quarantined table of old numbers is not, and a test that cannot tell them
    apart would force the history to be falsified.
    """
    text = path.read_text(encoding="utf-8")
    return re.sub(r"<details>.*?</details>", "", text, flags=re.DOTALL)


def test_the_documented_fold_count_is_the_one_in_the_artifact():
    """Four live sentences said 56; the artifact says 55, and so did the banner.

    Nothing compared them. The count had been right for a fixture scored at a
    midnight origin, and stayed in the prose after `DEFAULT_CUTOFF_HOUR` moved to
    midday and the answer became 55 — on the real panel *and* on the fixture.
    """
    folds = json.loads((REPO / "metrics" / "model.json").read_text(encoding="utf-8"))["backtest"][
        "folds"
    ]

    for name in ("README.md", "docs/writeup.md"):
        prose = _live_prose(REPO / name)
        claims = re.findall(r"(\d{2}) (?:daily folds|fold\b|refits|walk-forward refits)", prose)
        assert claims, f"{name} no longer states a fold count in live prose"
        for claim in claims:
            assert int(claim) == folds, (
                f"{name} claims {claim} folds; metrics/model.json records {folds}"
            )


def test_the_three_statements_of_the_test_runtime_agree():
    """They disagreed with each other and all three were wrong.

    README and CONTRIBUTING said `~20 s`, `docs/PUBLICATION-READY.md` said
    `~16 s`, and three consecutive runs measured 25-27 s. The absolute number is
    machine-dependent and pinning it would make this test flaky on a slower
    runner — but *three files stating three different numbers* is not
    machine-dependent, and that is the defect this catches.
    """
    seen = {}
    for name in ("CONTRIBUTING.md", "docs/PUBLICATION-READY.md"):
        text = (REPO / name).read_text(encoding="utf-8")
        found = re.findall(r"uv run pytest[^\n]*?~(\d+) s", text)
        assert found, f"{name} no longer states a runtime for `uv run pytest`"
        seen[name] = set(found)

    values = set().union(*seen.values())
    assert len(values) == 1, f"the pytest runtime is stated inconsistently: {seen}"


def test_any_lane_number_in_prose_is_read_from_an_artifact():
    """Armed before there is anything to arm it against, and that is the point.

    `metrics/foundation.json` does not exist until the dispatch run, so a pin
    written as "every lane number matches the artifact" is **vacuously green**
    today and stays green until the day someone writes the first sentence about
    the lane — which is exactly when nobody is looking at this test.

    So the assertion is conditional and fires on the *prose*: the moment the
    README names a foundation-lane arm, a published artifact has to exist for the
    number to have come from. Until then it records, in a runnable place, that the
    obligation is outstanding.
    """
    readme = _live_prose(REPO / "README.md")
    arm_names = ("chronos_bolt", "lgbm_17_demand_only", "lgbm_12_no_calendar", "lgbm_12_frozen")
    mentions = [name for name in arm_names if name in readme]
    if not mentions:
        return

    published = REPO / "metrics" / "foundation.json"
    assert published.exists(), (
        f"README names lane arm(s) {mentions} but metrics/foundation.json does not "
        "exist — the numbers beside them cannot have come from a published artifact"
    )
    payload = json.loads(published.read_text(encoding="utf-8"))
    assert payload["is_real"] is True
    assert payload["failed_gate"] is None, (
        f"the lane artifact was refused by {payload['failed_gate']}; its numbers must not be quoted"
    )


def test_the_documented_feature_count_is_the_real_one():
    """`**Features (20)**` in the README, against `FEATURE_COLUMNS`.

    Added after the prose beside it was found describing eight rolling features
    where the code has five: "rolling mean/std/min/max of the last 24 h and
    168 h" reads as four windows twice over, but only the 24 h window has all
    four — 168 h has the mean alone. The total, 20, happened to be right, which
    is what let the breakdown drift unnoticed. This pins the total; the
    breakdown is prose and stays a human's job.
    """
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    match = re.search(r"\*\*Features \((\d+)\)\*\*", readme)
    assert match, "README.md no longer states the feature count as `**Features (N)**`"
    assert int(match.group(1)) == len(build.FEATURE_COLUMNS), (
        f"README claims {match.group(1)} features; "
        f"features.build.FEATURE_COLUMNS has {len(build.FEATURE_COLUMNS)}"
    )
