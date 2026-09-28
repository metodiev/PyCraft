# CI/CD Pipelines: Stages, Gates and Scheduling

A pipeline is a program that runs on every change, so it deserves the same care as the code it tests. Two properties decide whether it earns that cost: how quickly it gives a useful answer, and whether its answer can be trusted.

## Jobs form a dependency graph

A flat list of steps maximises the time until failure. Modelling the work as a directed acyclic graph lets independent jobs run concurrently and keeps the cheap, decisive jobs early:

```yaml
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install ruff && ruff check .
  unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -r requirements.txt && pytest -q tests/unit
  integration:
    needs: [unit]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -r requirements.txt && pytest -q tests/integration
  package:
    needs: [unit, lint]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: ./scripts/build.sh
```

`lint` and `unit` start together; `package` waits for both; `integration` only runs if the unit tests passed. The scheduler walks the graph — topological order, with nodes at the same depth dispatched in parallel, bounded by runner capacity. When a job fails, everything downstream is skipped rather than started, unless the edge is explicitly marked as tolerant of failure (`if: always()` in GitHub Actions, `allow_failure: true` in GitLab), which is the correct marking for a security scan whose finding should be reported but not block a merge yet.

Two scheduling traps recur. A job with no dependency does not queue behind anything, so an expensive job placed at the top level runs on every commit even when an earlier failure would have made it pointless. And a cycle is not caught by a linter: the scheduler reports it late or not at all, so keep the graph shallow enough to hold in your head.

## Pass artifacts, do not rebuild

A job that re-installs dependencies and re-compiles the project for each downstream stage wastes the exact minutes you were trying to save. Build once, store the result, and hand it on:

- Artifacts are immutable once published. Downstream jobs pull by name and digest; a checksum mismatch is a stop condition, not a warning, because it means the tested bytes are not the deployed bytes.
- Cache the dependency directories, keyed on the lockfile hash. `actions/cache` with `hashFiles('**/requirements.txt')` restores the wheel cache on a hit and spends nothing on a miss. The key decides correctness: a key that omits the lockfile silently reuses stale dependencies.
- Compile-time constants belong in the artifact, not in the deployment environment. If a flag changes what was tested, it must change the artifact.

## Gates only work if they are trustworthy

A required status check on a protected branch is a contract: the merge button is disabled until named jobs report success. That makes the pipeline the enforcement point for review-free policy — no direct pushes, no force pushes — and it means the *names* of the required jobs are load-bearing. Rename a job and the branch protection is waiting on a check that will never appear; remove the check and the branch is unprotected.

A flaky gate destroys all of this. A test that fails one run in twenty trains developers to press re-run, and the first thing they stop reading is the failure output. Re-running does not distinguish "the code is broken" from "the test is broken", so the gate degrades into a delay rather than a signal. The same applies to a pipeline that fails on an unpinned lint rule released upstream. When a gate is red for reasons unrelated to the change, quarantine the test and fix it — do not widen the retry budget.

## Triggers and schedules

Runs are started by events: pushes, pull requests, tags, manual dispatch, and cron. Scheduled runs cover things that no commit triggers — a nightly dependency audit, a stale-branch cleanup, a full test matrix too slow for every push. Keep the classification explicit, because a scheduled job and a push job that share configuration fail differently: a nightly build against a moved `latest` base image fails when nobody is watching, so its failure needs a notification path of its own.

For unmerged pull requests, prefer running the pipeline on the merge result rather than on the branch tip. Some platforms expose this directly; where they do not, the branch can pass locally and fail after merge because another change landed underneath it.

## Rolling out a deploy

Deployment is the one stage where the blast radius is not just the build. The safe default is to shift traffic gradually and decide with measurements rather than hope:

1. Deploy the new version to a subset of instances or a small percentage of traffic, alongside the old one.
2. Watch the signals that indicate user-visible failure — error rate, latency percentiles, restart counts — against the previous version, with the same window and the same aggregation.
3. Either promote to all traffic or abandon, keeping the previous version live until promotion completes so a rollback is a traffic shift rather than a redeploy.
4. Make the decision automatic where possible: a canary held for a fixed number of minutes without a metric breach promotes itself, and a breach reverts without waking anyone.

A canary can only prove *no new errors in the observed window*. It is a detection mechanism, not a guarantee, and it must run on representative traffic: a canary fed only health checks and no user requests proves nothing at all. Roll back by shifting weight, not by rebuilding the previous release, because the rollback path is exercised under pressure and must be the simplest thing you own.

## Practice

[CI Pipeline Scheduler](../challenges/cloud-devops-ci-pipeline-scheduler) asks you to build the scheduler itself: produce a deterministic topological order, group jobs into parallel waves, propagate failures through edges including those marked tolerant, report cycles precisely, and account for cache hits when you decide what to run.
