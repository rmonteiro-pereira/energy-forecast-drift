"""The published surface has to keep its own promises.

This repository is going to be read by people who did not write it, and the one
thing that must never happen is a fixture number being mistaken for a
measurement. Every other guard against that is prose -- a README banner, a
docstring, a code review. Prose does not fail a build.

These tests are the part that does. They assert three invariants about the
files in `metrics/`, which is the only directory this project publishes:

1.  Every artifact answers `is_real` at the same top-level key. A consumer must
    never have to know which artifact nests it where, because the failure mode
    of guessing wrong is `None`, which is falsy, which silently reads as "not
    synthetic" -- the wrong answer in the safe-looking direction.

2.  `is_real` is true **only** when the provenance block also says the data is
    real. This is the one that matters. It does not hardcode `false`, because
    the day the EIA key lands the correct value becomes `true` and a test
    demanding `false` forever would just be deleted. What it forbids is the
    combination that would constitute a lie: a synthetic fixture published
    under a real flag.

3.  While the data is synthetic, the artifact carries a warning that actually
    says so, and the human-readable tables carry it in their first lines.

Committing a doctored artifact fails these. That is the entire point.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
METRICS = REPO / "metrics"

#: The artifacts the daily pipeline and the model entrypoints publish.
JSON_ARTIFACTS = sorted(p.name for p in METRICS.glob("*.json"))

#: The rendered tables a human reads instead of the JSON.
MARKDOWN_ARTIFACTS = sorted(p.name for p in METRICS.glob("*.md"))

#: Words that make a warning an actual warning rather than a label.
WARNING_MARKERS = ("SYNTHETIC", "NOT a benchmark")


def load(name: str) -> dict:
    return json.loads((METRICS / name).read_text(encoding="utf-8"))


def test_there_are_artifacts_to_check():
    """Guard against the suite passing vacuously if `metrics/` is ever emptied."""
    assert JSON_ARTIFACTS, "no metrics/*.json found — the other tests would pass vacuously"
    assert MARKDOWN_ARTIFACTS, "no metrics/*.md found — same problem"


@pytest.mark.parametrize("name", JSON_ARTIFACTS)
def test_every_artifact_answers_is_real_at_the_top_level(name: str):
    artifact = load(name)
    assert "is_real" in artifact, (
        f"{name} does not expose `is_real` at the top level. A consumer reading "
        "artifact['is_real'] would get None, which is falsy, which reads as "
        "'not synthetic' by accident. Publish the flag at the same key everywhere."
    )
    assert isinstance(artifact["is_real"], bool), (
        f"{name}: `is_real` must be a bool, not {type(artifact['is_real']).__name__} — "
        "a truthy string like 'false' is exactly the bug this checks for"
    )


@pytest.mark.parametrize("name", JSON_ARTIFACTS)
def test_is_real_is_never_true_over_synthetic_data(name: str):
    """The invariant that survives the key landing.

    Not "is_real is false" -- that expires. "is_real is true only if the data is
    really real" does not.
    """
    artifact = load(name)
    provenance = artifact.get("data")
    if not isinstance(provenance, dict) or "is_real" not in provenance:
        pytest.skip(f"{name} carries no nested provenance block to cross-check")

    if artifact["is_real"]:
        assert provenance["is_real"] is True, (
            f"{name} claims is_real=True while its own provenance block says the "
            f"underlying data is not real (kind={provenance.get('kind')!r}). That "
            "combination is a false claim about where the numbers came from."
        )
        assert provenance.get("kind") != "synthetic_fixture", (
            f"{name} claims is_real=True with kind='synthetic_fixture'."
        )


@pytest.mark.parametrize("name", JSON_ARTIFACTS)
def test_synthetic_artifacts_carry_a_real_warning(name: str):
    artifact = load(name)
    if artifact["is_real"]:
        pytest.skip(f"{name} is real data — no warning expected")

    warning = artifact.get("warning")
    assert warning, f"{name} is synthetic but carries no top-level `warning`"
    for marker in WARNING_MARKERS:
        assert marker.lower() in warning.lower(), (
            f"{name}: the warning does not contain {marker!r}. It reads: {warning!r}"
        )


@pytest.mark.parametrize("name", MARKDOWN_ARTIFACTS)
def test_rendered_tables_warn_above_the_numbers(name: str):
    """A human reads the markdown, so the warning has to reach them first."""
    text = (METRICS / name).read_text(encoding="utf-8")
    head = "\n".join(text.splitlines()[:6])

    # Only assert the warning when the companion JSON says the data is synthetic.
    stem = name.removesuffix("_table.md").removesuffix("_summary.md").removesuffix(".md")
    companion = next((j for j in JSON_ARTIFACTS if j.startswith(stem)), None)
    if companion and load(companion)["is_real"]:
        pytest.skip(f"{name} describes real data")

    assert "SYNTHETIC" in head.upper(), (
        f"{name}: the first six lines do not warn that the numbers are synthetic. They are:\n{head}"
    )
    first_table_row = next(
        (i for i, line in enumerate(text.splitlines()) if line.startswith("|")), None
    )
    if first_table_row is not None:
        warning_row = next(
            i for i, line in enumerate(text.splitlines()) if "SYNTHETIC" in line.upper()
        )
        assert warning_row < first_table_row, (
            f"{name}: the warning appears after the first table row — it has to come first"
        )


def test_readme_leads_with_the_synthetic_banner():
    """First thing in the file, and rendered as an alert rather than a blockquote.

    GitHub always puts the file listing above the README, so nothing here can be
    in the literal first viewport. What *can* be controlled is that the warning is
    the first thing inside the README and that it renders in GitHub's red
    `caution` style rather than as a grey blockquote a reader's eye slides past.
    """
    lines = (REPO / "README.md").read_text(encoding="utf-8").splitlines()
    head_lines = lines[:12]
    head = "\n".join(head_lines).upper()

    assert "SYNTHETIC" in head, (
        "the README's first 12 lines do not say the data is synthetic — "
        "a reviewer skimming the top of the page would not know"
    )
    assert "BENCHMARK" in head, (
        "the README's first 12 lines do not say these numbers are not a benchmark"
    )
    assert any(line.strip() == "> [!CAUTION]" for line in head_lines), (
        "the banner is not a GitHub `> [!CAUTION]` alert. Without it the block "
        "renders as a plain grey blockquote — legible, but not alarming, which "
        "defeats the point of leading with it."
    )

    # Nothing may come between the H1 and the banner.
    body = [line for line in head_lines if line.strip()]
    assert body[0].startswith("# "), f"README does not open with an H1: {body[0]!r}"
    assert body[1].strip() == "> [!CAUTION]", (
        f"something sits between the title and the warning: {body[1]!r}"
    )
