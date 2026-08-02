"""The workflow YAMLs are code, so they get tested like code.

A broken workflow is normally discovered by pushing a commit and watching a red
tick, which is a slow feedback loop for a repo that has no remote yet. Parsing
both files here catches a syntax error immediately, and the rest of the
assertions pin down the properties that make the daily cron safe to leave
scheduled: it fires once a day and off the hour, it stays runnable by hand, it
refuses to run without a key, and it stages explicit paths only.

Those first two replaced an earlier pair that held the cron *inert*. That was
the right guard until run 30725157840 promoted a champion — a cron before then
would have published a daily verdict about a model nobody had promoted. The
guards were rewritten for the activated state rather than deleted, because a
trigger nothing asserts on is how a `* * * * *` lands quietly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"
CI = WORKFLOWS / "ci.yml"
DAILY = WORKFLOWS / "daily.yml"
TRAIN = WORKFLOWS / "train.yml"


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def steps_of(workflow: dict, job: str) -> list[dict]:
    return workflow["jobs"][job]["steps"]


def run_commands(workflow: dict, job: str, strip_comments: bool = False) -> str:
    """Every `run:` block of a job, concatenated.

    `strip_comments` drops shell comment lines — the workflow explains itself
    inline, and a test looking for a dangerous command must not match the
    sentence warning against it.
    """
    text = "\n".join(step.get("run", "") for step in steps_of(workflow, job))
    if not strip_comments:
        return text
    return "\n".join(line for line in text.splitlines() if not line.strip().startswith("#"))


@pytest.mark.parametrize("path", [CI, DAILY, TRAIN], ids=["ci", "daily", "train"])
def test_the_workflow_parses(path):
    workflow = load(path)
    assert workflow["name"]
    assert workflow["jobs"], "a workflow with no jobs would silently do nothing"


# ---------------------------------------------------------------------------
# daily.yml — the live cron
# ---------------------------------------------------------------------------
def test_every_workflow_pins_the_same_major_of_a_shared_action():
    """One workflow must not silently hold an action back.

    This nearly shipped: Dependabot bumped `actions/checkout` 4 -> 7,
    `astral-sh/setup-uv` 5 -> 7, `actions/cache` 4 -> 6 and
    `actions/upload-artifact` 4 -> 7 on `main`, while a feature branch still
    carried the old majors in a *new* workflow file and a *new* job. Merging it
    would have quietly reverted four accepted upgrades — no conflict, no red
    tick, because nothing compared them.

    Same shape as the Python-version drift in `tests/test_toolchain.py`: two
    places state a version, nothing checks they agree.
    """
    used: dict[str, set[str]] = {}
    for path in sorted(WORKFLOWS.glob("*.yml")):
        workflow = load(path)
        for job in workflow["jobs"].values():
            for step in job.get("steps", []):
                uses = str(step.get("uses", ""))
                if "@" not in uses:
                    continue
                action, _, version = uses.partition("@")
                used.setdefault(action, set()).add(version)

    assert used, "no `uses:` entries found — did the workflow layout change?"

    inconsistent = {a: sorted(v) for a, v in used.items() if len(v) > 1}
    assert not inconsistent, (
        f"the same action is pinned at different versions across workflows: "
        f"{inconsistent}. Bring them together, or a dependency bump merged on "
        "one file gets reverted by another."
    )


def test_no_workflow_action_is_left_unpinned():
    """`uses: foo/bar` with no `@version` follows the default branch of a third party."""
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for job in load(path)["jobs"].values():
            for step in job.get("steps", []):
                uses = str(step.get("uses", ""))
                if uses and not uses.startswith("./"):
                    assert "@" in uses, f"{path.name}: `{uses}` is not pinned to a version"


def test_the_daily_cron_is_live_and_still_hand_runnable():
    """Activated 2026-08-02, once a champion existed to monitor.

    This replaces `test_the_daily_cron_is_still_inert`, which held the schedule
    commented out. That guard was right until run 30725157840 promoted a
    champion: before it, a cron published a daily verdict about a model nobody
    had promoted. Deleting it outright would have left the trigger unguarded,
    so what it protected is re-stated for the activated state.

    `on:` parses to the boolean `True` in YAML 1.1 — that is not a bug here,
    just PyYAML being faithful to the spec.
    """
    triggers = load(DAILY)[True]
    assert "schedule" in triggers, "the daily cron is meant to be live"
    assert "workflow_dispatch" in triggers, (
        "the manual trigger must survive activation — a scheduled job with no "
        "hand-run path can only be debugged by waiting for tomorrow"
    )


def test_the_daily_cron_fires_once_a_day_and_off_the_hour():
    """The cadence is a cost and a courtesy, and both are easy to lose in an edit.

    Once a day: the EIA publishes about twice daily, so anything faster spends
    API quota and Actions minutes to recompute windows that have not moved. An
    accidental `* * * * *` would be green, quiet and expensive — nothing else
    here would notice.

    Off the hour: GitHub throttles the top-of-hour stampede and delays those
    runs, so `20 6` is deliberate rather than decorative.
    """
    schedules = load(DAILY)[True]["schedule"]
    assert len(schedules) == 1, f"expected exactly one cron entry, found {len(schedules)}"

    minute, hour, dom, month, dow = schedules[0]["cron"].split()

    assert minute.isdigit() and int(minute) != 0, (
        f"minute is `{minute}`; it must be a fixed, non-zero minute so the run "
        "does not land in the top-of-hour queue GitHub throttles"
    )
    assert hour.isdigit(), f"hour is `{hour}`; a wildcard hour runs this 24 times a day"
    assert (dom, month, dow) == ("*", "*", "*"), (
        f"expected a plain daily schedule, got day-of-month={dom} month={month} day-of-week={dow}"
    )


def test_the_activation_prose_does_not_still_ask_for_activation():
    """Replaces `test_the_schedule_is_drafted_in_a_comment_ready_to_uncomment`.

    That test asserted the header carried a `# schedule:` draft and a
    `# TO ACTIVATE` checklist. Both were correct while the cron was dormant and
    both became lies the moment it fired — and a header telling a reader to
    uncomment a block that is already live is exactly the stale-prose failure
    `test_doc_claims.py` exists to catch elsewhere. So the guard is inverted
    rather than dropped: the instructions must be gone now that the state they
    described is gone.
    """
    text = DAILY.read_text(encoding="utf-8")

    assert "# TO ACTIVATE" not in text, (
        "the header still carries the pre-activation checklist; the cron is live"
    )
    assert "# schedule:" not in text, (
        "the header still carries a commented-out `schedule:` draft next to a "
        "live one — a reader cannot tell which is in force"
    )
    assert "uncomment the `schedule:` block" not in text, (
        "the header still tells a reader to uncomment a block that is already live"
    )


def test_the_daily_workflow_calls_exactly_the_pipeline_entrypoint():
    """One command, not a pipeline spread across YAML steps."""
    commands = run_commands(load(DAILY), "pipeline")
    assert "python -m pipeline.daily" in commands

    for legacy in ("python -m models", "python -m drift.run", "python -m ingest"):
        assert legacy not in commands, (
            f"`{legacy}` is called directly from the workflow; the daily job must go "
            "through pipeline.daily so the whole chain stays testable locally"
        )


def test_the_daily_workflow_fails_fast_without_a_key():
    commands = run_commands(load(DAILY), "pipeline")
    assert "--require-eia-key" in commands, (
        "without this flag a cron would silently publish synthetic fixture numbers"
    )


def test_the_daily_workflow_goes_dormant_rather_than_red_without_a_key():
    """No key must mean "did nothing, green", not "failed, red".

    The repository is public, so the Actions tab is part of what a visitor reads.
    A red X on the only scheduled workflow says "this is broken"; the truth is
    "this is waiting for a free API key". The safety rule is unchanged either
    way -- doing no work publishes nothing, which satisfies it more completely
    than failing does.
    """
    daily = load(DAILY)
    every = steps_of(daily, "pipeline")

    preflight = [s for s in every if s.get("id") == "preflight"]
    assert len(preflight) == 1, "the daily job has no single `preflight` step"
    assert preflight[0].get("env", {}).get("EIA_API_KEY") == "${{ secrets.EIA_API_KEY }}", (
        "the preflight step cannot see the secret it is meant to test for"
    )
    assert "has_key" in preflight[0].get("run", ""), (
        "the preflight step does not publish a `has_key` output"
    )

    guard = "steps.preflight.outputs.has_key == 'true'"

    # Every step that installs, computes, writes or pushes must be gated.
    must_be_gated = [
        s
        for s in every
        if s is not preflight[0] and s.get("uses", "").split("@")[0] != "actions/checkout"
    ]
    ungated = [
        s.get("name", s.get("uses", "?"))
        for s in must_be_gated
        if guard not in str(s.get("if", ""))
    ]
    assert not ungated, (
        f"these steps run even when no key is configured, so the job would do work "
        f"and could go red on a dormant repo: {ungated}"
    )


def test_the_cache_is_saved_only_after_a_successful_run():
    """A failed run must not persist half-updated state for every later run.

    `actions/cache/save` under `always()` would cache a partially written
    `data/`, `mlflow.db` or `mlruns/` after a mid-pipeline failure — and since
    the next run restores from that key, one bad run would poison all of them
    with no visible symptom. Losing a delta pull costs one API call; restoring
    corrupt MLflow state costs a debugging session.

    The upload-artifact step is deliberately the opposite: it *should* run on
    failure, because a failed run that explains itself is the point of it.
    """
    steps = steps_of(load(DAILY), "pipeline")

    save = [s for s in steps if s.get("uses", "").startswith("actions/cache/save")]
    assert len(save) == 1, "expected exactly one cache/save step"
    condition = str(save[0].get("if", ""))
    assert "always()" not in condition, (
        "cache/save runs under always(); a failed run would cache broken state "
        f"and every later run would restore it. Condition: {condition!r}"
    )
    assert "success()" in condition, f"cache/save should be gated on success(): {condition!r}"

    upload = [s for s in steps if s.get("uses", "").startswith("actions/upload-artifact")]
    assert len(upload) == 1
    assert "always()" in str(upload[0].get("if", "")), (
        "the run record must still be uploaded when the pipeline fails — that is "
        "when it is most worth reading"
    )


def test_the_dormant_path_never_weakens_the_publish_guard():
    """Going quiet must not become a way to publish fixture numbers."""
    commands = run_commands(load(DAILY), "pipeline")
    # The real run still refuses to publish without a key, for the case the
    # secret exists but is empty or rejected part-way through.
    assert "--require-eia-key" in commands
    assert "--source real" in commands, (
        "the daily run must ask for real data explicitly; falling back to the "
        "fixture is what --require-eia-key exists to prevent"
    )
    assert "--source synthetic" not in commands, (
        "the daily workflow must never run against the fixture"
    )


def test_the_key_reaches_the_job_as_a_secret_and_is_never_echoed():
    daily = load(DAILY)
    text = DAILY.read_text(encoding="utf-8")

    env = [step.get("env", {}) for step in steps_of(daily, "pipeline")]
    assert any(e.get("EIA_API_KEY") == "${{ secrets.EIA_API_KEY }}" for e in env)

    lowered = text.lower()
    assert "echo $eia_api_key" not in lowered
    assert "echo ${{ secrets" not in lowered


def test_the_commit_step_stages_explicit_paths_only():
    """`git add metrics/` is one .gitignore mistake away from committing the lake."""
    commands = run_commands(load(DAILY), "pipeline", strip_comments=True)
    adds = [line.strip() for line in commands.splitlines() if line.strip().startswith("git add")]
    assert adds == ["git add metrics/forecast.json \\"], adds
    assert "git add ." not in commands
    assert "git add -A" not in commands
    assert "git add metrics/\n" not in commands


def test_the_committed_paths_are_exactly_what_the_pipeline_writes():
    from pipeline import daily as pipeline_daily

    commands = run_commands(load(DAILY), "pipeline")
    written = {
        pipeline_daily.FORECAST_JSON,
        pipeline_daily.MONITOR_JSON,
        pipeline_daily.DRIFT_JSON,
        pipeline_daily.DRIFT_SUMMARY,
        pipeline_daily.RUN_JSON,
        pipeline_daily.FORECAST_PNG,
        pipeline_daily.ROLLING_PNG,
    }
    for name in written:
        assert f"metrics/{name}" in commands, f"{name} is written but never committed"


def test_the_publish_step_never_pushes_at_protected_main():
    """A bot pushing at a protected branch can only ever be rejected.

    Not a hypothetical. Run 30718525099 ingested two years of real EIA demand,
    scored it, ran the drift check — and the last line died with
    `GH006: Protected branch update failed for refs/heads/main.` /
    `Required status check "test" is expected.` The whole pipeline was green
    and it published nothing, because `github-actions[bot]` is not an admin and
    so does not inherit the `enforce_admins: false` bypass.

    Comments are stripped: the step explains that failure inline, so a test
    matching against the raw block would be satisfied by the prose describing
    the bug rather than by the code avoiding it.
    """
    commands = run_commands(load(DAILY), "pipeline", strip_comments=True)
    pushes = [line.strip() for line in commands.splitlines() if line.strip().startswith("git push")]
    assert pushes, "the daily job no longer pushes anything — nothing can reach the repo"
    for push in pushes:
        assert "refs/heads/" in push, (
            f"`{push}` pushes at whatever the checkout is on, which is `main`. "
            "`main` is protected and requires the `test` check, so this is "
            "rejected with GH006 after the pipeline has already done all its work"
        )
        assert "refs/heads/main" not in push, (
            f"`{push}` targets the protected branch explicitly; it will be declined"
        )
        assert "--force" not in push and " -f " not in f" {push} ", (
            f"`{push}` forces. An unattended job must not force: it is "
            "unreviewable, and it lets a later run rewrite a PR while somebody "
            "is reading it. The per-run branch name exists so no force is needed"
        )


def test_the_metrics_commit_never_skips_ci():
    """`[skip ci]` and a required check are mutually exclusive.

    `test` is required on `main`. A commit carrying `[skip ci]` never runs it,
    so the check never reports, so the PR sits on "Expected — Waiting for
    status to be reported" forever and can never be merged. The old push-to-main
    step had `[skip ci]` and it was harmless there only because that push was
    rejected anyway; carried into a PR flow it becomes a deadlock.

    Exactly the defect issue #19 documents for the `mutate` check, one branch
    over — see `tests/test_mutation_config.py`.
    """
    commands = run_commands(load(DAILY), "pipeline", strip_comments=True)
    for marker in ("[skip ci]", "[ci skip]", "[no ci]", "skip-checks"):
        assert marker not in commands, (
            f"the metrics commit carries `{marker}`, so the required `test` check "
            "never reports and the PR can never be merged"
        )


def test_the_job_holds_the_permissions_its_publish_step_needs():
    """Measured, not assumed: `contents: write` here is what actually escalates.

    The repo sits on `default_workflow_permissions: "read"`, and the header of
    `daily.yml` used to say that had to be switched to "Read and write". It does
    not: run 30718525099 reached the *branch protection* hook, which a read-only
    token never does — it would have been a 403, not GH006. So this block is
    load-bearing on its own, and `pull-requests: write` is what the PR step adds.
    """
    permissions = load(DAILY)["permissions"]
    assert permissions.get("contents") == "write", (
        "without `contents: write` the token cannot push the metrics branch"
    )
    assert permissions.get("pull-requests") == "write", (
        "the publish step opens a PR; without `pull-requests: write` it 403s"
    )


def test_the_publish_step_tolerates_one_named_failure_and_no_others():
    """The degradation must stay narrow, or it becomes a silent-green switch.

    One failure is legitimately not a bug: `gh pr create` refuses when "Allow
    GitHub Actions to create and approve pull requests" is off. The branch is
    already pushed by then and only a click is missing, so that case warns.
    Every other failure — auth, network, a wrong base, a rejected push — must
    still go red. A blanket `|| true` or `continue-on-error` here is precisely
    how a publish step reports success having published nothing.
    """
    steps = steps_of(load(DAILY), "pipeline")
    publish = [s for s in steps if "PR" in s.get("name", "")]
    assert len(publish) == 1, "expected exactly one step that opens the metrics PR"
    assert not publish[0].get("continue-on-error"), (
        "continue-on-error on the publish step makes every failure invisible"
    )

    body = str(publish[0].get("run", ""))
    stripped = "\n".join(line for line in body.splitlines() if not line.lstrip().startswith("#"))
    assert "set -euo pipefail" in stripped, (
        "without `set -e` a failing command mid-step leaves the step green"
    )
    assert "|| true" not in stripped, "a blanket `|| true` swallows every failure"
    assert stripped.rstrip().endswith("exit 1"), (
        "the fall-through of the error branch must fail; if it ends any other "
        "way, an unrecognised `gh pr create` failure exits 0"
    )


def _publish_step_body() -> str:
    """The publish step's `run:` block with shell comments stripped.

    Stripped for the reason the whole file strips: this step explains its own
    history inline — including the sentence describing the close loop it no
    longer has — and a test matching raw text would be satisfied by the
    explanation instead of the code.
    """
    steps = steps_of(load(DAILY), "pipeline")
    publish = [s for s in steps if "PR" in s.get("name", "")]
    assert len(publish) == 1, "expected exactly one step that opens the metrics PR"
    return "\n".join(
        line
        for line in str(publish[0].get("run", "")).splitlines()
        if not line.lstrip().startswith("#")
    )


def test_the_publish_step_never_discards_an_unpublished_refresh():
    """Closing yesterday's metrics PR threw away a day that never published.

    The step used to "supersede": open today's PR, close yesterday's. An *open*
    metrics PR is by definition one that was never merged, so that loop deleted
    a day's numbers on the way to tidying up. It matters because every run
    recomputes fixed rolling windows (`drift/config.py`) — the week-over-week
    accumulation this project exists to show lives only in the git history of
    merged refreshes. The tidying was deleting the product.

    Merged predecessors leave the `open` list by themselves. The ones that
    linger are exactly the days that failed, and they must stay visible.
    """
    body = _publish_step_body()
    assert "gh pr close" not in body, (
        "the publish step closes an earlier metrics PR. If that PR is open it "
        "was never merged, so this discards a day that was never published"
    )
    assert "--delete-branch" not in body, (
        "deleting the branch of an unmerged metrics PR destroys the only copy of that day's numbers"
    )


def test_the_publish_step_arms_auto_merge():
    """A refresh needing a human every morning is a chore with a cron attached.

    Branch protection still decides: `--auto` publishes only what `test` and
    `mutate` have already passed, and queues rather than merging if they have
    not. Without it, the daily job produces a PR a day that nobody merges — and
    an unmerged day is a lost day.
    """
    body = _publish_step_body()
    assert "gh pr merge" in body, "nothing ever merges the PR this step opens"
    assert "--auto" in body, (
        "`gh pr merge` without `--auto` would merge regardless of the checks, "
        "walking straight past the honesty gates in ci.yml"
    )


def test_the_publish_step_goes_red_once_days_stack_up_unpublished():
    """Two days is a hiccup; three is a broken publish path.

    Counted before the new PR exists, so it never counts itself. Zero is the
    healthy state — yesterday merged and left the open list. Anything else must
    be loud, and past a couple of days the job must stop quietly manufacturing
    work nobody is reading.
    """
    body = _publish_step_body()
    assert "unpublished" in body, "nothing counts the refreshes that never merged"
    assert "-ge 3" in body, "no threshold turns a stalled publish path red"
    assert "::warning" in body, "a stalled publish path passes without an annotation"


def test_every_swallowed_failure_announces_itself():
    """A tolerated failure that says nothing is indistinguishable from success.

    Two failures here are legitimately not bugs — `gh pr create` refused by repo
    policy, and `gh pr merge --auto` refused when auto-merge is off — because in
    both the commit is already pushed and the day is not lost. Neither may pass
    silently: the whole failure mode this workflow was rewritten to escape is a
    publish step reporting success having published nothing.
    """
    body = _publish_step_body()
    for line in body.splitlines():
        if "||" not in line:
            continue
        assert "::warning" in line or "echo" in line, (
            f"`{line.strip()}` swallows a failure without announcing it"
        )
        assert "|| true" not in line, f"`{line.strip()}` is a blanket tolerance"


# ---------------------------------------------------------------------------
# train.yml — the workflow that makes a champion exist at all
# ---------------------------------------------------------------------------
def test_training_never_promotes_a_model_fitted_on_the_fixture():
    """A champion promoted off fixture data would then be *served* as real.

    `models.train --source real` raises rather than falling back, so a green run
    proves the numbers came from the API. `--source synthetic` stays reachable
    for a dry run, but it has to be asked for by name at dispatch time — the
    default is `real`, and nothing hardcodes the fixture.
    """
    train = load(TRAIN)
    commands = run_commands(train, "train", strip_comments=True)

    assert "python -m models.train" in commands, "the training workflow does not train"
    assert "--source synthetic" not in commands, (
        "the workflow pins the fixture as its source; a model promoted off "
        "fixture data would be served as though it were real"
    )

    choice = train[True]["workflow_dispatch"]["inputs"]["source"]
    assert choice["default"] == "real", (
        f"the dispatch default is {choice['default']!r}; the safe path must be the "
        "one you get by pressing the button without thinking"
    )


def test_training_goes_red_without_a_key_rather_than_quietly_doing_nothing():
    """The opposite choice from daily.yml, and deliberately so.

    `daily.yml` goes dormant-green without a key because it is scheduled and a
    red X on a public repo's only cron reads as "this project is broken". A
    training run is dispatched by hand: nobody triggers one by accident, so a
    silent green would just hide that nothing was trained.
    """
    steps = steps_of(load(TRAIN), "train")
    preflight = [s for s in steps if s.get("id") == "preflight"]
    assert len(preflight) == 1, "the training job has no preflight step"

    body = str(preflight[0].get("run", ""))
    assert preflight[0].get("env", {}).get("EIA_API_KEY") == "${{ secrets.EIA_API_KEY }}", (
        "the preflight step cannot see the secret it is meant to test for"
    )
    assert "exit 1" in body, "a missing key leaves the training run green"


def test_the_registry_is_persisted_somewhere_that_does_not_evict():
    """A cache is an accelerator with an eviction policy, not a store.

    `data/` surviving on a cache is fine — a full refresh re-pulled two years in
    43 seconds. The registry is not like that: promotion decisions and lineage
    cannot be re-derived from anywhere, so the only copy must not live behind an
    eviction policy. One release per run, never clobbered, so the previous
    champion stays retrievable.
    """
    commands = run_commands(load(TRAIN), "train", strip_comments=True)
    assert "gh release create" in commands, (
        "the registry is never published anywhere durable, so the only copy is "
        "the Actions cache — and an evicted cache takes the lineage with it"
    )
    assert "--clobber" not in commands, (
        "clobbering a single release asset overwrites the previous registry, "
        "which is the durability this step exists to provide"
    )
    assert "mlflow.db" in commands and "mlruns" in commands, (
        "the published archive does not contain the registry state"
    )


def test_training_hands_the_champion_to_the_daily_job():
    """Published durably AND cached, or the next daily run still finds nothing.

    `daily.yml` restores by the `lake-` prefix. Saving under the same prefix is
    what makes the champion reachable without any further wiring; the release
    asset is the copy that outlives the cache.
    """
    steps = steps_of(load(TRAIN), "train")
    save = [s for s in steps if s.get("uses", "").startswith("actions/cache/save")]
    assert len(save) == 1, "expected exactly one cache/save step"
    assert str(save[0]["with"]["key"]).startswith("lake-"), (
        "the training run saves under a key daily.yml will never restore from"
    )
    assert "success()" in str(save[0].get("if", "")), (
        "caching after a failed training run persists a half-written registry, "
        "and every later run restores it"
    )


def test_training_never_writes_to_the_repository():
    """It publishes an artifact; it must not touch `main` or open PRs.

    Two producers writing `metrics/` is the concurrency hazard that makes a
    split-role setup go wrong. This job's output is a release asset and a cache
    entry, nothing else.
    """
    commands = run_commands(load(TRAIN), "train", strip_comments=True)
    for forbidden in ("git push", "git commit", "gh pr create", "gh pr merge"):
        assert forbidden not in commands, (
            f"the training workflow runs `{forbidden}`; it must not be a second "
            "writer of the repository"
        )


def test_concurrency_stops_two_runs_writing_metrics_at_once():
    assert load(DAILY)["concurrency"]["group"]
    assert load(DAILY)["concurrency"]["cancel-in-progress"] is False


# ---------------------------------------------------------------------------
# ci.yml
# ---------------------------------------------------------------------------
def test_ci_lints_and_tests():
    commands = run_commands(load(CI), "test")
    assert "ruff check" in commands
    assert "pytest" in commands


def test_ci_smoke_tests_the_pipeline_and_the_drift_alarm():
    commands = run_commands(load(CI), "test")
    assert "python -m pipeline.daily" in commands
    assert "--simulate-shift" in commands, "CI must prove the drift alarm still fires"


def test_ci_guards_the_things_that_must_never_be_committed():
    commands = run_commands(load(CI), "test")
    assert "mlruns" in commands
    assert "5M" in commands, "the metrics/ size guard is what keeps the repo small"
