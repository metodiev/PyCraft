# Flaky Test Detector

A test that fails once a week is worse than a test that always fails: it burns
review time, gets `@pytest.mark.skip`-ed, and teaches the team to ignore red. The
fix is a quality gate that reads run history and flags tests whose outcome
depends on something other than the code — deterministically, with no statistics
library and no randomness of its own.

## Your task

Implement `detect_flaky(history)`.

`history` is a list of runs, oldest first. Each run maps a test id to one of the
strings `"passed"`, `"failed"` or `"skipped"`.

Return a `dict` mapping each **flaky** test id to a dict describing it:

| Key | Value |
| --- | ----- |
| `"outcomes"` | `dict[str, int]` counting only `"passed"` and `"failed"`, e.g. `{"passed": 3, "failed": 2}`. Keys with a zero count are omitted. |
| `"flips"` | `int` — how many times the `passed`/`failed` status changed between **consecutive executed runs**. |
| `"first_flip_run"` | `int` — 0-based index of the run that contained the *second* executed outcome of that test, i.e. where a flip first becomes possible. |

### What counts as flaky

A test is flaky when it has **both** at least one `"passed"` and at least one
`"failed"` outcome across the whole history.

Rules:

* `"skipped"` runs are invisible: they are not counted in `outcomes`, do not
  break a flip streak, and do not set `first_flip_run`. A test that is only ever
  `"passed"` and `"skipped"` is **not** flaky.
* A test missing from a run entirely is treated exactly like `"skipped"`: the
  run is skipped over for that test.
* Flips are counted between consecutive *executed* (non-skipped) outcomes. So
  `passed, skipped, failed` has `flips == 1`.
* `first_flip_run` is the index of the run holding the test's **second** executed
  outcome, regardless of whether that outcome differs from the first.
* Empty history returns `{}`. Runs that are missing tests never add keys.
* The result must contain no non-flaky tests at all.

## Examples

```python
history = [
    {"a": "passed", "b": "passed"},
    {"a": "failed", "b": "passed"},
    {"a": "passed", "b": "passed"},
]
detect_flaky(history)
# {"a": {"outcomes": {"passed": 2, "failed": 1}, "flips": 2, "first_flip_run": 1}}

detect_flaky([{"a": "passed"}, {"a": "skipped"}, {"a": "passed"}])   # {} — never failed
detect_flaky([{"a": "failed"}, {"a": "failed"}])                    # {} — never passed
detect_flaky([])                                                    # {}
```

## Constraints

* Standard library only.
* The function must not mutate `history` or any run inside it.
* Order of keys in the returned dict is not checked.
* No I/O, no printing.

## Hints

<details>
<summary>Hint 1 — Two passes are clearer than one</summary>

Collect the executed outcomes per test id first, keeping the run index with each
one:

```python
timeline = {}                      # test id -> list[(run_index, outcome)]
for index, run in enumerate(history):
    for test_id, outcome in run.items():
        if outcome == "skipped":
            continue
        timeline.setdefault(test_id, []).append((index, outcome))
```

Then a test is flaky iff `len({outcome for _, outcome in entries}) == 2`, and the
remaining two fields are one-liners over `entries`.

</details>

<details>
<summary>Hint 2 — Counting flips</summary>

Compare neighbouring entries of the executed timeline, not of the raw runs:

```python
flips = sum(
    1
    for (_, previous), (_, current) in zip(entries, entries[1:])
    if previous != current
)
```

`first_flip_run` is simply `entries[1][0]` — but only report it for flaky tests,
and index a two-element list only after you know it is long enough.
</details>
