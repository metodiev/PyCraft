def to_dict(instance):
    """Convert a dataclass instance into plain ``dict``/``list``/scalar data.

    Nested dataclasses are converted recursively; tuples become lists and dict
    keys/values are converted too. ``TypeError`` is raised for non-dataclasses.

    >>> from dataclasses import dataclass
    >>> @dataclass
    ... class Point:
    ...     x: int
    ...     y: int
    >>> to_dict(Point(1, 2))
    {'x': 1, 'y': 2}
    """
    # TODO: validate that ``instance`` is a dataclass and convert it recursively.
    raise NotImplementedError("Complete the to_dict function")


def from_dict(cls, data):
    """Rebuild ``cls`` from ``data``, validating every declared field.

    Raises ``TypeError`` for wrong value types and ``ValueError`` for missing or
    unknown fields. ``data`` is never mutated.

    >>> from dataclasses import dataclass
    >>> @dataclass
    ... class Point:
    ...     x: int
    ...     y: int
    >>> from_dict(Point, {"x": 1, "y": 2}) == Point(1, 2)
    True
    """
    # TODO: read the type hints, reject unknown/missing fields and validate values.
    raise NotImplementedError("Complete the from_dict function")
