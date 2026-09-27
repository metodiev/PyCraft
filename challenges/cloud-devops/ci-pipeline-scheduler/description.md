# CI Pipeline Scheduler

A pipeline is a DAG: `build` before `test` before `deploy`, with everything that
has no unmet dependency free to run at the same time. Getting the *order* right
is the easy half. The hard half is what happens when something fails — a red
`lint` with `allow_failure: true` must not stop the release, but a red `build`
must stop everything downstream, and a job that never ran must not be treated as
a cache warm.

Implement the scheduler.

## Your task

Implement `execution_order`, `parallel_waves` and `schedule` in `solution.py`,
plus the `PipelineCycleError` exception.

A job is a dict with:

| Key | Meaning |
| --- | --- |
| `"name"` | unique, non-empty job name (required) |
| `"needs"` | list of job names that must run first (default `[]`) |
| `"cache"` | cache key, or `None`/absent for no caching (default `None`) |
| `"allow_failure"` | `True` when this job's failure must not block its dependents (default `False`) |

Two exceptions:

* `PipelineError(ValueError)` — the pipeline is not usable: a duplicate name, a
  `needs` entry naming an unknown job, a malformed job, or a `failures` entry
  naming an unknown job.
* `PipelineCycleError(PipelineError)` — a dependency cycle. It must expose the
  cycle's participants, sorted, on `.jobs`, and name them in its message.

### `execution_order(jobs)`

Return the job names in a valid dependency-respecting order. When several jobs
are ready at once, take the alphabetically first, one at a time (Kahn's
algorithm with a name tie-break) — so the order depends only on the pipeline,
never on how the `jobs` list happened to be written. An empty pipeline is `[]`.

### `parallel_waves(jobs)`

Group the jobs into waves that can each run in parallel. A job belongs one wave
after the **latest** of its dependencies (a job with no dependencies is in wave
0), and names inside a wave are sorted:

```python
parallel_waves([{"name": "a"}, {"name": "b", "needs": ["a"]},
                {"name": "c", "needs": ["a", "b"]}])
# [['a'], ['b'], ['c']]
```

### `schedule(jobs, failures=())`

Walk the pipeline in `execution_order` and give every job a status:

* `"skipped"` — some dependency was `"skipped"`, **or** some dependency was
  `"failed"` while `allow_failure` is false for *that dependency*. A skipped
  dependency blocks just as a hard failure does.
* `"failed"` — the job ran and its name is in `failures`.
* `"success"` — the job ran and passed.

Return:

| Key | Value |
| --- | --- |
| `"statuses"` | `{name: status}` for every job |
| `"order"` | `execution_order(jobs)` |
| `"waves"` | `parallel_waves(jobs)` |
| `"cache_hits"` | names that *reused* a warm key, in execution order |
| `"cache_misses"` | names that *warmed* a key, in execution order |
| `"summary"` | `{"success": n, "failed": n, "skipped": n, "cache_hits": n}` |

Cache rules: a job with no cache key is excluded from both lists entirely. A job
that ran and whose key was warmed earlier in this run is a hit; otherwise it is
a miss and warms the key. A failed or skipped job **neither hits nor warms** the
cache — it has nothing to publish, so it must not shadow a later real build.

## Examples

```python
PIPELINE = [
    {"name": "build", "needs": [], "cache": "toolchain-v1"},
    {"name": "lint", "needs": [], "cache": None},
    {"name": "flaky", "needs": [], "cache": None, "allow_failure": True},
    {"name": "package", "needs": ["build"], "cache": "toolchain-v1"},
    {"name": "test", "needs": ["build"], "cache": None},
]

execution_order(PIPELINE)   # ['build', 'flaky', 'lint', 'package', 'test']
parallel_waves(PIPELINE)    # [['build', 'flaky', 'lint'], ['package', 'test']]

schedule(PIPELINE, failures=["build"])["statuses"]
# {'build': 'failed', 'flaky': 'success', 'lint': 'success',
#  'package': 'skipped', 'test': 'skipped'}

schedule(PIPELINE)["cache_hits"]   # ['package'] — it reuses build's key
```

## Constraints

* Standard library only.
* Deterministic: no wall-clock time, no randomness, no filesystem access.
* Do not mutate `jobs` or the job dicts.
* Ordering always comes from the graph — never from the order the jobs were
  passed in. `execution_order(list(reversed(PIPELINE)))` must equal
  `execution_order(PIPELINE)`.
* A cycle must be detected rather than looped on.

## Hints

<details>
<summary>Hint 1 — Two passes: validate, then order</summary>

Build a `{name: job}` index in one pass. While you are there, reject duplicates
and non-string names. Then resolve every `needs` entry against that index — an
unknown dependency is a `PipelineError` — and only afterwards start the ordering
loop. Mixing validation into the traversal is where keyword errors get swallowed.

</details>

<details>
<summary>Hint 2 — Kahn's algorithm with a name tie-break</summary>

`ready = sorted(name for name, needs in remaining.items() if needs <= emitted)`
is the whole algorithm: when `ready` is empty but jobs remain, there is a cycle.
Taking *one* job at a time from a freshly sorted `ready` set is what makes the
order stable.

</details>

<details>
<summary>Hint 3 — Naming the cycle's participants</summary>

Reporting "cycle detected" is easy and useless. The participants are the strongly
connected components of size > 1, which is Tarjan's algorithm — or, at these
sizes, a cheaper trick: repeatedly remove every job with no remaining
unemitted dependency; whatever is left when nothing more can be removed is
exactly the set of jobs on or inside a cycle.

```python
alive = set(by_name)
changed = True
while changed:
    changed = False
    for name in sorted(alive):
        if not any(need in alive and need != name for need in by_name[name]["needs"]):
            alive.discard(name)
            changed = True
```

That leaves the participants — and only them, so healthy jobs downstream of the
cycle are not named.
</details>
