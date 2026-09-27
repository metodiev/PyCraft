# Blast Radius Analysis

Before you harden anything, you need to know **what breaks when a component
breaks.** That is the question principal engineers are asked in incidents, and
it is answerable from the dependency graph alone.

Implement a blast-radius analyser in `solution.py`: three functions, each
answerable from the dependency graph alone.

## Your task

### `transitive_dependents(graph, component)`

Everything that stops working when `component` fails.

`graph` maps a component to the components it **depends on**:

```python
{
    "web":     ["api", "cdn"],
    "api":     ["db", "cache"],
    "db":      ["disk"],
    "cache":   ["redis"],
    "worker":  ["db"],
    "cdn":     [],
    "disk":    [],
    "redis":   [],
    "metrics": ["prometheus"],
    "prometheus": [],
}
```

If `api` fails, then `web` fails (it depends on `api`) and so does `worker`
only if it depends on `api`. The result is every component that can reach
`component` by following dependency edges, **excluding the component itself**,
returned sorted.

Dependencies are transitive: if `web → api → db`, then a `db` failure takes out
both `api` and `web`.

### `single_points_of_failure(graph)`

Components whose failure **alone** disconnects the most dependents.

Return the components ranked by the size of their blast radius, largest first,
ties broken by name. Include every component in the graph, even those with no
dependents, so the ranking is complete rather than filtered by an arbitrary
threshold.

### `critical_path(graph, target)`

The longest chain of dependencies that `target` depends on, as a list ending at
`target`.

For `web` in the example above, the path is `["disk", "db", "api", "web"]`.
This is the depth at which a failure is furthest from the surface: the number of
things that must all be healthy for `target` to work.

If two chains are equally long, choose the one that is **lexicographically
smallest** when compared from the far end, so the result is deterministic.

## Examples

```pycon
>>> graph = {"web": ["api"], "api": ["db"], "db": [], "worker": ["db"]}
>>> transitive_dependents(graph, "db")
['api', 'web', 'worker']
>>> critical_path(graph, "web")
['db', 'api', 'web']
```

## Constraints

- Standard library only.
- **Cycles must not hang the analyser.** A dependency graph in a real system can
  contain one, and an analyser that recurses forever is useless during an
  incident. Detect the cycle and raise `CycleError` naming the components.
- Self-dependency is a cycle.
- A component named in an edge but absent as a key is a leaf with no
  dependencies, not an error.
- Results must be deterministic and inputs must not be mutated.

## Hints

<details>
<summary>Hint 1 — "Reaches" is the reverse of "depends on"</summary>

`transitive_dependents` walks the edges *backwards*: you want everything with a
path **to** the failed component, not everything reachable **from** it. Build
the reverse index once rather than scanning the graph per node.

</details>

<details>
<summary>Hint 2 — Why every component appears in the ranking</summary>

Filtering the ranking to components with a large radius hides the long tail,
and the long tail is exactly where an unnoticed single point of failure lives.
Return them all; let the caller draw the line.

</details>

<details>
<summary>Hint 3 — Iterate, do not recurse</summary>

Python's recursion limit is a poor fit for a graph an operator typed in at 3am.
An explicit worklist with a `seen` set handles cycles gracefully and lets you
report *which* nodes formed the cycle.

</details>

<details>
<summary>Hint 4 — Lexicographic tie-breaks need a defined direction</summary>

Compare ties from the deepest end so `["disk", "db", "api", "web"]` beats
`["cache", "db", "api", "web"]`. Comparing from the surface end would prefer the
alphabetically earlier *target* neighbour instead, which is not what you want.
</details>
