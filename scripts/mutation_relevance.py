"""Decide whether a change can move the mutation score.

`.github/workflows/mutation.yml` used to make this decision with a `paths:`
filter on its `pull_request` trigger. That worked, but it meant the `mutate`
check did not exist at all on a PR that touched nothing relevant — and a check
that never reports cannot be a *required* check. GitHub leaves the pull request
at "Expected — Waiting for status to be reported" indefinitely, and there is no
native "skipped counts as success". Measured on two real PRs before branch
protection was enabled, neither #16 nor #18 produced a `mutate` check at all;
requiring it that day would have made both unmergeable, along with every future
docs-only PR.

So the trigger is now unconditional and the *work* is conditional instead. The
job always runs, this script decides in about a second whether the expensive
36-minute pass is needed, and the check therefore always reports.

Deliberately stdlib-only, and deliberately run by the system `python3` **before**
`uv sync`. Installing a dependency tree in order to decide whether to do any work
would spend a minute of the time this is here to save.

The pattern list lives in `.github/mutation-paths.txt` and is read from there by
this script *and* by `tests/test_mutation_config.py`, which recomputes the
first-party import closure from the AST and fails if the list is missing
anything. One file, two readers: two lists that must agree by hand is the
failure mode being designed out.

    python3 scripts/mutation_relevance.py --changed changed-files.txt
    git diff --name-only origin/main...HEAD | python3 scripts/mutation_relevance.py

Exits 0 either way — the answer is the output, not the exit code. Whether
anything matched is written to `$GITHUB_OUTPUT` as `relevant=true|false`.
"""

from __future__ import annotations

import argparse
import os
import sys
from fnmatch import fnmatch
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PATHS_FILE = REPO / ".github" / "mutation-paths.txt"


def load_patterns(path: Path | None = None) -> list[str]:
    """The canonical globs, with comments and blank lines stripped."""
    source = PATHS_FILE if path is None else path
    if not source.exists():
        sys.exit(
            f"{source} is missing. It is the single source of truth for which "
            "changes can move the mutation score; without it this job cannot "
            "tell a docs typo from a deleted assertion."
        )
    patterns = []
    for raw in source.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    if not patterns:
        sys.exit(f"{source} lists no patterns, so nothing would ever be considered relevant.")
    return patterns


def matches(path: str, patterns: list[str]) -> bool:
    """GitHub-style `paths:` matching, close enough for the globs we actually use.

    `fnmatch`'s `*` already crosses `/`, so `drift/**` and `drift/*` agree here;
    both forms are accepted so the list can be written the way GitHub documents
    it. Exact string equality is checked first so a pattern containing no
    wildcards means precisely itself.
    """
    normalised = path.strip().replace("\\", "/").lstrip("./")
    if not normalised:
        return False
    return any(
        normalised == pattern
        or fnmatch(normalised, pattern)
        or fnmatch(normalised, pattern.replace("**", "*"))
        for pattern in patterns
    )


def select(changed: list[str], patterns: list[str]) -> list[str]:
    """The subset of `changed` that can move the score, in the order given."""
    return [path for path in changed if matches(path, patterns)]


def _read_changed(args: argparse.Namespace) -> list[str]:
    text = Path(args.changed).read_text(encoding="utf-8") if args.changed else sys.stdin.read()
    return [line.strip() for line in text.splitlines() if line.strip()]


def _emit(name: str, value: str) -> None:
    """Write a step output, when there is a step to write it to."""
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")


def _summary(text: str) -> None:
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(text + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--changed",
        help="file holding the changed paths, one per line (default: stdin)",
    )
    parser.add_argument(
        "--paths-file",
        type=Path,
        default=None,
        help=f"the canonical glob list (default: {PATHS_FILE.relative_to(REPO)})",
    )
    args = parser.parse_args(argv)

    patterns = load_patterns(args.paths_file)
    changed = _read_changed(args)
    relevant = select(changed, patterns)

    if relevant:
        _emit("relevant", "true")
        listed = "\n".join(f"- `{path}`" for path in relevant[:20])
        more = f"\n- …and {len(relevant) - 20} more" if len(relevant) > 20 else ""
        print(f"{len(relevant)} of {len(changed)} changed paths can move the score:")
        print(listed + more)
        _summary(
            "## Mutation testing\n\n"
            f"{len(relevant)} of {len(changed)} changed paths can move the mutation "
            f"score, so the full pass is running.\n\n{listed}{more}\n"
        )
        return 0

    _emit("relevant", "false")
    print(f"None of the {len(changed)} changed paths can move the mutation score.")
    _summary(
        "## Mutation testing — skipped\n\n"
        f"None of the **{len(changed)}** changed paths match "
        "[`.github/mutation-paths.txt`](../blob/main/.github/mutation-paths.txt), "
        "the canonical list of files that can move the mutation score, so the "
        "36-minute pass was not run.\n\n"
        "This check still reports, deliberately: a required check that is skipped "
        "never reports at all, and GitHub would leave this pull request waiting on "
        "it forever.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
