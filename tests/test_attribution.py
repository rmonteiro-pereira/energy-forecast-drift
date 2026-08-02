"""The CC BY 4.0 credit is a licence condition, so it gets a test rather than a habit.

Open-Meteo publishes under CC BY 4.0. §3(a)(1) attaches the attribution
condition to *sharing* the licensed material **or an adaptation of it**, and it
attaches at each point of sharing — not once, somewhere in the repository. Two
surfaces publish figures derived from that data:

  * `docs/DRIFT-EVALUATION.md`, where `scripts/drift_eval_real_weather.py` turns
    hourly 2 m temperature into the PSI and KS table; and
  * the dashboard, which renders drift computed from the weather features and is
    served publicly.

Both are adapted material — the raw series is never redistributed, it is cached
under gitignored `reports/`. That is why §3(a)(1)(B), "indicate if You modified
the Licensed Material", is asserted too: crediting the source while implying the
numbers *are* the source would be the wrong credit, not a smaller one.

**Why co-location rather than presence.** The first version of this file asked
whether each signal appeared *anywhere* in the file, and a perturbation run
showed that is not a test. Deleting the entire attribution section from
`DRIFT-EVALUATION.md` left it green, because an unrelated inline link to
open-meteo.com further up satisfied the creator check, and the word "modified"
survived in prose about something else. Attribution that a reader cannot see as
one statement is not attribution, so the assertion is that the three elements
occur inside one window of text.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# Wide enough to span a credit written as a short paragraph plus its
# modification notice; far too narrow to span a whole document. Both surfaces
# fit comfortably inside it today.
WINDOW = 900

CREATOR = re.compile(r"open-meteo\.com", re.IGNORECASE)
LICENCE_LINK = re.compile(r"creativecommons\.org/licenses/by/4\.0", re.IGNORECASE)
LICENCE_NAME = re.compile(r"CC[\s-]?BY[\s-]?4\.0", re.IGNORECASE)
MODIFIED = re.compile(r"\bmodified\b|\badapt(?:ed|ation)\b", re.IGNORECASE)

DISPLAY_SURFACES = [
    pytest.param(
        "docs/DRIFT-EVALUATION.md",
        id="the drift evaluation, which publishes the derived PSI and KS table",
    ),
    pytest.param(
        "dashboard/src/App.tsx",
        id="the dashboard, which renders drift computed from the weather features",
    ),
]


def attribution_windows(text: str) -> list[str]:
    """Every stretch of `text` that names the creator, sized to a credit.

    Anchored on the creator because that is the one element with nowhere else to
    live: the licence and the modification notice are only meaningful next to
    whoever is being credited.
    """
    return [
        text[max(0, m.start() - WINDOW // 2) : m.end() + WINDOW // 2]
        for m in CREATOR.finditer(text)
    ]


@pytest.mark.parametrize("surface", DISPLAY_SURFACES)
def test_every_surface_that_displays_derived_weather_credits_open_meteo(surface: str):
    text = (REPO / surface).read_text(encoding="utf-8")

    assert CREATOR.search(text), (
        f"{surface} publishes figures derived from Open-Meteo data and does not "
        "name the creator. CC BY 4.0 §3(a)(1)(A)(i) requires it wherever the "
        "material or an adaptation is shared."
    )


@pytest.mark.parametrize("surface", DISPLAY_SURFACES)
def test_the_credit_carries_the_licence_beside_it_not_elsewhere(surface: str):
    """A licence named far from the credit is not the notice the clause asks for."""
    text = (REPO / surface).read_text(encoding="utf-8")

    assert any(
        LICENCE_NAME.search(window) and LICENCE_LINK.search(window)
        for window in attribution_windows(text)
    ), (
        f"{surface} never names CC BY 4.0 *and* links it within {WINDOW} characters "
        "of an Open-Meteo credit. §3(a)(1)(A)(iii) asks for a notice referring to "
        "the licence at the point of sharing; a name without a link leaves the "
        "reader unable to reach the terms, and a link elsewhere in the file is "
        "not something a reader of this page will ever see."
    )


@pytest.mark.parametrize("surface", DISPLAY_SURFACES)
def test_the_credit_says_the_data_was_modified(surface: str):
    """§3(a)(1)(B). These are statistics over the series, not the series."""
    text = (REPO / surface).read_text(encoding="utf-8")

    assert any(MODIFIED.search(window) for window in attribution_windows(text)), (
        f"{surface} credits Open-Meteo without indicating, beside that credit, "
        "that the published figures are adapted material. Crediting the source "
        "while implying the numbers are the source is the wrong credit."
    )
