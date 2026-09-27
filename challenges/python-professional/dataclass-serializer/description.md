# Dataclass Serializer

APIs hand you JSON: nested dicts, lists, and — the moment a human edits it — a
string where you expected a number. `dataclasses.asdict` handles the easy
direction and does nothing about validation. Build the pair of functions a
service layer actually needs.

## Your task

Implement `to_dict(instance)` and `from_dict(cls, data)` for `@dataclass`
classes, driven by the declared type hints.

### `to_dict(instance)`

* Returns a plain `dict`.
* Nested dataclass values become dicts, recursively.
* `list`/`tuple` become a `list` with their elements converted recursively
  (`list[Item]` becomes `list[dict]`).
* `dict` becomes a `dict` with both keys and values converted recursively.
* `None` stays `None`.

### `from_dict(cls, data)`

Rebuild `cls` from `data`, validating as it goes:

| Problem | Raise |
| ------- | ----- |
| `data` is not a mapping | `TypeError` |
| A field with no default is missing | `ValueError` |
| `data` has a key that is not a declared field | `ValueError` |
| A value does not match the declared type | `TypeError` |

Type rules (apply to nested values too):

| Declared type | Accepts |
| ------------- | ------- |
| `int` | `int` only. `True`/`False` and floats are **rejected**. |
| `float` | `int` or `float`. Booleans are rejected. |
| `bool` | `bool` only. |
| `str` | `str` only. |
| `list[...]` / `tuple[...]` / `dict[...]` | the matching container, with every element validated |
| a nested dataclass | a mapping, parsed recursively |
| `X \| None` / `Optional[X]` | `None`, or a valid `X` |
| unannotated / `Any` | anything |

`from_dict` must not mutate `data`.

## Examples

```python
from dataclasses import dataclass, field

@dataclass
class Point:
    x: int
    y: int

@dataclass
class Segment:
    start: Point
    labels: list[str] = field(default_factory=list)
    note: str | None = None

s = Segment(start=Point(1, 2), labels=["a"], note=None)
to_dict(s)        # {"start": {"x": 1, "y": 2}, "labels": ["a"], "note": None}
from_dict(Segment, {"start": {"x": 1, "y": 2}, "labels": ["a"], "note": None}) == s   # True

from_dict(Point, {"x": 1, "y": True})   # TypeError  (bool is not an int)
from_dict(Point, {"x": 1})              # ValueError (missing y)
from_dict(Point, {"x": 1, "y": 2, "z": 3})   # ValueError (unknown field)
```

## Constraints

* Standard library only: `dataclasses`, `typing` and `inspect` are expected.
* Preserve dataclass defaults: an omitted field that has a default is simply not
  passed to the constructor, so `default_factory` values are fresh per instance.
* `to_dict(instance)` accepts only dataclass instances — anything else raises
  `TypeError`.
* Round-trip stability is required: `from_dict(cls, to_dict(obj)) == obj`.

## Hints

<details>
<summary>Hint 1 — Read the annotations once</summary>

`typing.get_type_hints(cls)` resolves string annotations into real objects, and
`dataclasses.fields(cls)` gives you the declared fields (including their
defaults). Walk the field list rather than `data.items()` so unknown keys are
easy to reject:

```python
import dataclasses, typing

hints = typing.get_type_hints(cls)
known = {f.name for f in dataclasses.fields(cls)}
unknown = set(data) - known
if unknown:
    raise ValueError(f"unknown fields: {sorted(unknown)}")
```

</details>

<details>
<summary>Hint 2 — Validating one value against its annotation</summary>

Handle the annotation in layers — union first, then containers, then dataclasses,
then primitives — and recurse with the same helper for inner types. `typing.get_origin`
and `typing.get_args` split `list[Point]` into `list` and `(Point,)`:

```python
origin = typing.get_origin(annotation)      # list, dict, types.UnionType, ...
args = typing.get_args(annotation)          # (Point,) for list[Point]
```

For the `int` rule, remember `isinstance(True, int)` is `True`, so check
`isinstance(value, bool)` **before** accepting an `int`.
</details>
