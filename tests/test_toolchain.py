"""The toolchain must agree with itself.

Written after a CI failure that had nothing to do with the code. `pyproject.toml`
declared `requires-python = ">=3.11"`, so uv installed the newest Python on the
runner (3.12) — while `[tool.mypy] python_version = "3.11"` told mypy to analyse
under 3.11 rules. mypy then read numpy's stubs from the 3.12 site-packages, hit a
`type` statement that only parses on 3.12+, and failed:

    numpy/__init__.pyi:737: error: Type statement is only supported in
    Python 3.12 and greater  [syntax]

Locally it passed, because the local venv happened to be 3.11. That is the
"green laptop, red runner" failure mode, and the second instance of it in this
repository — the first was `uv add --dev` writing to `[dependency-groups]` while
CI installed `--extra dev`.

Both had the same shape: two places state a version or a location, nothing
checks they agree, and the disagreement only shows up on a machine that is not
the author's. These tests check the agreement.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PYPROJECT = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
PYTHON_VERSION_FILE = REPO / ".python-version"
CI_WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"


def pinned_version() -> str:
    """The interpreter `uv` will actually resolve, from `.python-version`."""
    assert PYTHON_VERSION_FILE.exists(), (
        ".python-version is missing. Without it uv picks the newest Python on "
        "the machine, so CI and a laptop can silently run different interpreters."
    )
    return PYTHON_VERSION_FILE.read_text(encoding="utf-8").strip()


def test_the_pinned_interpreter_is_a_bare_minor_version():
    version = pinned_version()
    parts = version.split(".")
    assert len(parts) == 2 and all(p.isdigit() for p in parts), (
        f".python-version should pin a minor version like '3.11', got {version!r}"
    )


def test_mypy_analyses_the_version_that_is_actually_installed():
    """The exact mismatch that broke CI.

    mypy reads stubs out of the installed interpreter's site-packages, so
    `python_version` must match the interpreter, not merely satisfy the floor.
    """
    mypy_target = PYPROJECT["tool"]["mypy"]["python_version"]
    assert mypy_target == pinned_version(), (
        f"[tool.mypy] python_version is {mypy_target!r} but .python-version pins "
        f"{pinned_version()!r}. mypy would analyse under one version's rules while "
        "reading another version's stubs — which fails on stubs that use syntax "
        "newer than the target, with an error that points at a dependency rather "
        "than at this codebase."
    )


def test_the_pinned_interpreter_satisfies_the_declared_floor():
    floor = PYPROJECT["project"]["requires-python"]
    assert floor.startswith(">="), f"unexpected requires-python form: {floor!r}"
    floor_parts = tuple(int(p) for p in floor.removeprefix(">=").strip().split("."))
    pinned_parts = tuple(int(p) for p in pinned_version().split("."))
    assert pinned_parts >= floor_parts, (
        f".python-version pins {pinned_version()} but requires-python is {floor}"
    )


def test_ci_states_the_same_interpreter_as_the_pin():
    """Belt and braces: the version is visible in the workflow, not only a dotfile."""
    yaml = pytest.importorskip("yaml")
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))

    setup = [
        step
        for step in workflow["jobs"]["test"]["steps"]
        if str(step.get("uses", "")).startswith("astral-sh/setup-uv")
    ]
    assert len(setup) == 1, "expected exactly one setup-uv step in ci.yml"

    declared = str(setup[0].get("with", {}).get("python-version", "")).strip()
    assert declared == pinned_version(), (
        f"ci.yml pins python-version {declared!r} but .python-version says {pinned_version()!r}"
    )


def test_the_running_interpreter_matches_the_pin():
    """Reports a mismatch; does not fail the suite for one.

    This deliberately **skips** rather than fails when the interpreter differs
    from the pin. Running on another Python is legitimate — `requires-python` is
    `>=3.11`, the suite passes on 3.12, and a version matrix would run several on
    purpose. What is not legitimate is *mypy's target* disagreeing with the
    interpreter it reads stubs from, and that is pinned by
    `test_mypy_analyses_the_version_that_is_actually_installed` above, which is
    static and always applies.

    An earlier version of this test asserted equality, and it failed the whole
    suite on 3.12 for no reason other than the version number. It was written to
    catch a stale venv and instead punished a correct one.
    """
    running = f"{sys.version_info.major}.{sys.version_info.minor}"
    if running != pinned_version():
        pytest.skip(
            f"running Python {running}, .python-version pins {pinned_version()}. "
            "Fine if deliberate (a matrix job, or checking a newer Python); if not, "
            "re-run `uv sync --extra dev` so local runs match CI. Note that "
            "`uv run mypy` targets the pinned version, so type-check results from "
            "this interpreter are not what CI will produce."
        )
    assert running == pinned_version()
