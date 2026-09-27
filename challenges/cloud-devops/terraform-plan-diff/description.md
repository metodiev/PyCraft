# Terraform Plan Diff

`terraform plan` is a diff between two states of the world: what the
configuration declares, and what the provider actually reports. The interesting
part is not the diff — it is the *plan*: which changes can happen together,
which force a rebuild, and what order they must happen in so nothing is torn
down while something still depends on it.

Build that reconciler over plain dicts.

## Your task

Implement four functions in `solution.py`. A resource is addressed as
`"<type>.<name>"` (e.g. `"aws_vpc.main"`, `"module.network"`) and its body is a
dict of attribute names to values. Attribute values may be nested dicts, lists
or strings.

### `resource_type(address)`

Return the type half of an address: `resource_type("aws_vpc.main") == "aws_vpc"`,
`resource_type("module.network") == "module"`. Raise `ValueError` when the
address has no `.name` part (`"aws_vpc"`, `"aws_vpc."`, `""`).

### `dependency_graph(resources)`

`resources` maps addresses to bodies. Return `{address: [dependencies]}` with
one key per address, each list **sorted** and deduplicated.

An address `B` is a dependency of `A` when any string inside `A`'s body contains
`"${B}"` or `"${B}."` — the interpolation forms `${aws_vpc.main}` and
`${aws_vpc.main.id}`. Scan values recursively (nested dicts and lists included).
Ignore references to unknown addresses and self-references. A non-mapping body
raises `ValueError`.

### `diff_resources(desired, actual, immutable=None)`

`desired` maps addresses to bodies, or to `None` to declare that the resource
must not exist. `actual` maps addresses to the bodies the provider reports.
`immutable` maps a resource **type** to the set of attribute names that force
replacement (`{"aws_instance": {"ami", "availability_zone"}}`).

Return a list of change dicts, one per address in `sorted(desired | actual)`
order, each with:

| Key | Value |
| --- | --- |
| `"address"` | the address |
| `"resource_type"` | `resource_type(address)` |
| `"action"` | `"create"`, `"update"`, `"replace"`, `"delete"` or `"no-op"` |
| `"changed"` | sorted names of the attributes that differ |

Rules:

* In `actual` but not desired (or declared `None`) → `delete`, and `changed` is
  `[]`. A declared `None` that is also absent from `actual` produces **no entry
  at all** — there is nothing to destroy.
* In desired but not in `actual` → `create`, and `changed` lists every declared
  attribute name.
* In both → only the attributes **the configuration declares** are compared.
  Attributes the state reports on its own (provider-computed values, extra
  tags) are not changes, and a declared attribute that is missing from the state
  *is* one. No differences at all → `no-op`.
* A difference in an attribute that is listed as immutable for this resource
  type → `replace`; any other difference → `update`. `replace` wins when both
  kinds changed.
* Never mutate `desired`, `actual` or their bodies.

### `plan(desired, actual, immutable=None)`

Return `{"changes": [...], "summary": {...}}`.

`"changes"` is the `diff_resources` output ordered so that it is safe to apply:

* Applies (`create`/`update`/`replace`/`no-op`) come first, in dependency order
  — a resource is listed after every resource it references. The graph is built
  from the state the plan produces: `actual` overlaid with every desired body.
* Destroys come last, in reverse dependency order — a dependent is destroyed
  before the resource it references.
* Ties are broken by ascending address, so the same inputs always produce the
  same list, whatever order the input dicts happen to be in.

`"summary"` counts each action plus a `"total"`:

```python
{"create": 1, "update": 0, "replace": 1, "delete": 2, "no-op": 3, "total": 7}
```

## Examples

```python
DESIRED = {
    "aws_vpc.main": {"cidr_block": "10.0.0.0/16"},
    "aws_subnet.public": {
        "vpc_id": "${aws_vpc.main.id}",
        "cidr_block": "10.0.1.0/24",
    },
}
ACTUAL = {"aws_vpc.main": {"cidr_block": "10.0.0.0/16", "id": "vpc-1"}}

dependency_graph(DESIRED)
# {"aws_vpc.main": [], "aws_subnet.public": ["aws_vpc.main"]}

diff_resources(DESIRED, ACTUAL)
# [{"address": "aws_subnet.public", "resource_type": "aws_subnet",
#   "action": "create", "changed": ["cidr_block", "vpc_id"]},
#  {"address": "aws_vpc.main", "resource_type": "aws_vpc",
#   "action": "no-op", "changed": []}]

diff_resources(
    {"aws_instance.web": {"ami": "ami-2"}},
    {"aws_instance.web": {"ami": "ami-1"}},
    {"aws_instance": {"ami"}},
)   # one "replace" change with changed == ["ami"]

plan({"module.network": {"vpc_id": "${aws_vpc.main.id}"}}, {"aws_vpc.main": {}})
# changes: aws_vpc.main (create) then module.network (create)

plan({}, {"aws_vpc.main": {}, "module.network": {"vpc_id": "${aws_vpc.main.id}"}})
# changes: module.network (delete) then aws_vpc.main (delete)
```

## Constraints

* Standard library only (`re` is optional; a substring test is enough).
* Deterministic: no wall-clock time, no randomness, no filesystem access.
* Command order is always deterministic — sort tie-breaks by address.
* A reference cycle must not hang: emit the blocked addresses in ascending order
  once nothing else is ready, so every resource appears exactly once.

## Hints

<details>
<summary>Hint 1 — Two graphs, opposite directions</summary>

Creates are "who must come before me?" (block on my dependencies). Destroys are
"who must go before me?" (block on my *dependents*). Compute the second by
inverting the first:

```python
dependents = {address: [] for address in addresses}
for address, needs in graph.items():
    for need in needs:
        dependents[need].append(address)
```

</details>

<details>
<summary>Hint 2 — A tie-break that stays stable</summary>

Only comparing "is everything I need already emitted?" gives you a set; turn it
into a list with `sorted(...)` and emit the whole batch, then recompute. Sorting
the ready set each round is what makes the plan reproducible across runs and
across input dict orderings — and it costs nothing at these sizes.

</details>

<details>
<summary>Hint 3 — Declared versus reported attributes</summary>

Iterate the *desired* body, not the state:

```python
changed = sorted(
    name for name, value in wanted.items()
    if name not in current or current[name] != value
)
```

Iterating the state instead silently ignores an attribute your configuration sets
that the state has not caught up with yet — exactly the change you must plan.
</details>
