# Profiling: Measure Before You Optimise

Intuition about performance is wrong often enough to be dangerous. Programmers
reliably misjudge which function is hot, and they reliably optimise the code
they understand rather than the code that costs. Measure first, change one
thing, measure again.

## Decide what "fast enough" means first

A measurement without a target becomes an invitation to optimise forever. Before
touching a profiler, write down the budget: this endpoint must answer within
200 ms at p95, this batch job must finish inside its window, this function is
called once per row and must stay under ten microseconds. A number turns a
disagreement about style into a comparison of measurements, and it tells you when
to stop — which is just as important as knowing where to start.

## timeit for microbenchmarks

`timeit` runs a snippet many times and reports the best or mean duration. It
needs repetition because a single sample is dominated by noise: the first
iteration pays warm-up costs, and the OS can preempt any individual run.

```python
import timeit

setup = "data = list(range(1000))\nlookup = set(data)"
print(timeit.timeit("999 in data", setup=setup, number=10_000))
print(timeit.timeit("999 in lookup", setup=setup, number=10_000))
```

Read the numbers with care. `number` decides how many runs are timed: each run
should be short enough that timer granularity is irrelevant and long enough that
a few microseconds are meaningful. Keep the compared snippets as similar as
possible — here the sample above builds the set once in `setup`, because
`timeit.timeit("s = set(range(1000)); 999 in s")` spends its time constructing
the set, not searching it, and would report a misleading comparison.
`Timer` runs with garbage collection temporarily disabled, so if you are timing
allocation-heavy code, time the allocation *and* collection explicitly rather
than relying on the default.

Microbenchmarks tell you the cost of a `dict` lookup versus a `list` scan. They
do not tell you what matters in your program, because the call graph is not the
same as a tight loop.

## cProfile and pstats

For a real program, profile the whole run:

```python
import cProfile

cProfile.run("main()", "profile.out")
```

```bash
python -m pstats profile.out
```

Inside `pstats` the two commands worth knowing are `sort cumulative`, which
orders by the total time spent inside a function plus everything it called, and
`sort tottime`, which orders by time spent in the function's own bytecode only.
The distinction is the whole point.

`tottime` (own time) says "this function is expensive in itself". `cumulative`
says "everything below this function is expensive". A top-level orchestrator
will dominate the cumulative list while doing nothing itself — fixing it is
impossible because there is nothing to fix. Look down the cumulative list for a
function whose own time is also significant, or look at the boundary where
cumulative time stops being explained by children.

The same reading applies to `cProfile`'s `ncalls` column: a function with a
modest own time called a million times is often a better target than a
consistently slow function called twice. And beware profiler overhead —
`cProfile` adds per-call cost, which penalises many-small-calls code
disproportionately.

## Line-level detail

When a function is confirmed hot but you cannot see which statement is
responsible, per-line timers help. Tools in the `line_profiler` family wrap a
function and report hits and time per source line; CPython 3.12 also ships
`sys.monitoring`, which lets you observe line and call events with lower
overhead than tracing. The method is more important than the tool: you are
looking for the one line inside the hot function that consumes the time — a
repeated lookup, an allocation inside a loop, a call out to something expensive.
Without this step you optimise the function's style rather than its cost.

## Re-measure, and only then believe it

Every change gets a before/after measurement on the same input, with the same
Python version, and with a record of the number, not the feeling. Keep a note of
the shape: what was measured, on what data, and what changed.

Optimisations that survive this discipline share a property — they reduce the
*count* of expensive operations. Caching a result that was recomputed per row,
hoisting a lookup out of a loop, replacing a scan with a precomputed index,
streaming instead of materialising. Changes that only rearrange code without
removing work rarely show up, and if the measurement says "no change", reverting
the change is the correct response.

One more trap: a benchmark that is too small to reach the regime you care about.
If the production input is a million rows, a 100-row benchmark is measuring
interpreter overhead, not your algorithm's growth.

## Practice

Profile your solution to [Range Sum Queries](../challenges/performance-range-sum-queries)
before changing it: use `cProfile` to find whether your time sits in the build
step or in the query loop, fix the larger term, and re-run the same measurement
to confirm the win.
