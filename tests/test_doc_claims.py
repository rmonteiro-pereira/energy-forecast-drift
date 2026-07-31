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

import re
import subprocess
import sys
from pathlib import Path

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
