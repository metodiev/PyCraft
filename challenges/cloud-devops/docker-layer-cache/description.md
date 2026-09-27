# Docker Layer Cache Analysis

A build that takes eleven minutes because `COPY . .` sits above
`RUN pip install` is one of the most common — and most expensive — mistakes in
CI. This challenge makes the cost visible and computable.

Model Docker's build cache over a parsed Dockerfile.

## Your task

### `parse_dockerfile(text)`

Parse a Dockerfile into instructions, in order.

Return a list of `Instruction(keyword, argument)`. Rules:

- Keywords are upper-cased; `RUN`, `run` and `Run` are all `RUN`.
- Blank lines and lines whose first non-space character is `#` are ignored.
- A trailing `\` continues the instruction onto the next line, which is how a
  multi-line `RUN` is written. Join such lines into one instruction with the
  continuation removed, and **collapse runs of whitespace** in the argument so
  the same instruction always renders identically.
- A line that is not `KEYWORD rest` raises `DockerfileError`.

### `cache_miss_index(instructions, changed)`

The index of the **first** instruction that misses the cache.

`changed` is a set of tokens describing what changed: a path like `"src/app.py"`,
an argument name like `"ARG:PYTHON_VERSION"`, or `"__everything__"`.

Walk the instructions in order and decide, per instruction:

| Instruction | Misses when |
| ----------- | ----------- |
| `FROM` | always misses when `"__everything__"` is in `changed`; otherwise never |
| `ARG` / `ENV` | the instruction's own key is in `changed` |
| `COPY` / `ADD` | any changed path is covered by the instruction's source, **or** an earlier layer already missed |
| `RUN` / anything else | only when an earlier layer already missed |

The crucial part: **once a layer misses, every later layer misses too.** A
returned index therefore means "this layer and everything after it rebuilds".

Return `None` when nothing misses.

### `rebuild_cost(instructions, changed)`

How much work is thrown away:

- `misses` — instructions from the first miss onward;
- `rebuilds` — the same count;
- `skipped` — instructions before the first miss, i.e. the cache that survives;
- `ratio` — `skipped / total`, or `1.0` for an empty Dockerfile.

Return a `BuildCost`.

### `suggest_reorder(instructions)`

Move whole-context copies (`COPY . .` / `COPY . /app`, i.e. a source of `.`)
to **immediately after the last `RUN` instruction**, so a source edit stops
invalidating a dependency install.

Return the reordered list. Requirements:

- Preserve the relative order of everything else exactly.
- Preserve the relative order of the moved copies among themselves.
- If there is no whole-context copy, or no `RUN`, return the instructions
  unchanged.
- Do not mutate the input.

Reordering is not free — a `RUN` may genuinely need the source present — so this
is a *suggestion*, and the tests only check the ordering properties and that a
subsequent source change still produces the same miss index for the `RUN`.

## Examples

```pycon
>>> text = """FROM python:3.12
... WORKDIR /app
... COPY . .
... RUN pip install -r requirements.txt"""
>>> [i.keyword for i in parse_dockerfile(text)]
['FROM', 'WORKDIR', 'COPY', 'RUN']

>>> parse_dockerfile("RUN pip install \\\n    -r requirements.txt")[0].argument
'pip install -r requirements.txt'

>>> cache_miss_index(parse_dockerfile(text), {"src/app.py"})
2

>>> [i.keyword for i in suggest_reorder(parse_dockerfile(text))]
['FROM', 'WORKDIR', 'RUN', 'COPY']
```

The reordered build still misses on a source change, but the miss now lands on
the `COPY` — *after* the expensive install has been served from cache.

## Constraints

- Standard library only.
- Dockerfiles here are a realistic subset, not the full grammar: no heredocs,
  no multi-stage-specific handling beyond treating `FROM` as a layer.
- Deterministic; callers may pass sets, so never rely on their iteration order.
- Do not mutate the input list.

## Hints

<details>
<summary>Hint 1 — Why one miss cascades</summary>

A layer's cache key includes its parent's. If layer 3 changes, layer 4's parent
differs, so layer 4 misses regardless of its own content. That cascade is why
the *position* of a `COPY` matters more than its size.

</details>

<details>
<summary>Hint 2 — Coverage, not equality</summary>

`COPY src/ /app/src/` covers a change to `src/app.py`. Compare the changed path
against the instruction's source as a path prefix on segment boundaries —
`src/` must cover `src/app.py`, and `src/` must not cover `srcs/app.py`.

</details>

<details>
<summary>Hint 3 — Continuations before parsing</summary>

Join continuation lines first, then parse. Trying to parse line-by-line means
every multi-line `RUN` becomes several bogus instructions and the layer indices
shift.
</details>
