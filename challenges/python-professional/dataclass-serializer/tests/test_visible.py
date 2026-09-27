"""Visible tests — the learner sees these before submitting."""

import dataclasses

import pytest

from solution import from_dict, to_dict


@dataclasses.dataclass
class Point:
    x: int
    y: int


@dataclasses.dataclass
class Segment:
    start: Point
    labels: list[str] = dataclasses.field(default_factory=list)
    note: str | None = None


def test_simple_dataclass_round_trip():
    point = Point(1, 2)
    assert to_dict(point) == {"x": 1, "y": 2}
    assert from_dict(Point, {"x": 1, "y": 2}) == point


def test_nested_dataclass_is_converted():
    segment = Segment(start=Point(1, 2), labels=["a", "b"])
    assert to_dict(segment) == {"start": {"x": 1, "y": 2}, "labels": ["a", "b"], "note": None}
    assert from_dict(Segment, to_dict(segment)) == segment


def test_missing_and_unknown_fields_raise_value_error():
    with pytest.raises(ValueError):
        from_dict(Point, {"x": 1})
    with pytest.raises(ValueError):
        from_dict(Point, {"x": 1, "y": 2, "z": 3})


def test_wrong_types_raise_type_error():
    with pytest.raises(TypeError):
        from_dict(Point, {"x": "one", "y": 2})
    with pytest.raises(TypeError):
        to_dict({"x": 1})
