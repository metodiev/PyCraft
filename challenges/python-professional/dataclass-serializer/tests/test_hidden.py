"""Hidden tests — graded on Submit, never shown to the learner."""

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


@dataclasses.dataclass
class Mixed:
    ratio: float
    flag: bool
    name: str
    points: list[Point] = dataclasses.field(default_factory=list)
    lookup: dict[str, int] = dataclasses.field(default_factory=dict)
    maybe: Point | None = None


def test_bool_is_not_an_int_but_floats_accept_ints():
    with pytest.raises(TypeError):
        from_dict(Point, {"x": True, "y": 2})
    with pytest.raises(TypeError):
        from_dict(Point, {"x": 1.0, "y": 2})
    assert from_dict(Mixed, {"ratio": 3, "flag": True, "name": "n"}).ratio == 3
    with pytest.raises(TypeError):
        from_dict(Mixed, {"ratio": True, "flag": True, "name": "n"})


def test_bool_rejects_ints_and_int_lists_reject_bools():
    with pytest.raises(TypeError):
        from_dict(Mixed, {"ratio": 1.0, "flag": 1, "name": "n"})
    with pytest.raises(TypeError):
        from_dict(Mixed, {"ratio": 1.0, "flag": True, "name": "n", "points": [{"x": True, "y": 1}]})


def test_containers_are_validated_element_by_element():
    with pytest.raises(TypeError):
        from_dict(Mixed, {"ratio": 1.0, "flag": True, "name": "n", "points": {"x": 1}})
    with pytest.raises(ValueError):
        from_dict(Mixed, {"ratio": 1.0, "flag": True, "name": "n", "points": [{"x": 1}]})
    with pytest.raises(TypeError):
        from_dict(Mixed, {"ratio": 1.0, "flag": True, "name": "n", "lookup": {"a": "b"}})
    parsed = from_dict(
        Mixed,
        {
            "ratio": 2,
            "flag": False,
            "name": "n",
            "points": [{"x": 1, "y": 2}],
            "lookup": {"a": 1},
        },
    )
    assert parsed.points == [Point(1, 2)]
    assert parsed.lookup == {"a": 1}


def test_optional_fields_accept_none_and_reject_wrong_types():
    parsed = from_dict(Mixed, {"ratio": 1.0, "flag": True, "name": "n", "maybe": None})
    assert parsed.maybe is None
    nested = from_dict(Mixed, {"ratio": 1.0, "flag": True, "name": "n", "maybe": {"x": 1, "y": 2}})
    assert nested.maybe == Point(1, 2)
    with pytest.raises(TypeError):
        from_dict(Mixed, {"ratio": 1.0, "flag": True, "name": "n", "maybe": 7})


def test_unknown_and_missing_fields_are_rejected_at_any_depth():
    with pytest.raises(ValueError):
        from_dict(Mixed, {"ratio": 1.0, "flag": True, "name": "n", "extra": 1})
    with pytest.raises(ValueError):
        from_dict(Mixed, {"ratio": 1.0, "flag": True})
    with pytest.raises(ValueError):
        from_dict(Segment, {"start": {"x": 1, "y": 2, "z": 3}})


def test_input_mapping_is_not_mutated_and_defaults_stay_fresh():
    payload = {"start": {"x": 1, "y": 2}}
    snapshot = {"start": {"x": 1, "y": 2}}
    first = from_dict(Segment, payload)
    second = from_dict(Segment, payload)
    assert payload == snapshot
    assert first.labels == [] and second.labels == []
    first.labels.append("only me")
    assert second.labels == []
    assert first.note is None


def test_nested_containers_round_trip():
    original = Mixed(
        ratio=1.5,
        flag=True,
        name="top",
        points=[Point(1, 2), Point(3, 4)],
        lookup={"a": 1, "b": 2},
        maybe=Point(0, 0),
    )
    assert from_dict(Mixed, to_dict(original)) == original
    assert to_dict(original)["points"] == [{"x": 1, "y": 2}, {"x": 3, "y": 4}]
