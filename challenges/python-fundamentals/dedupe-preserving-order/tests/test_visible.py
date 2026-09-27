"""Visible tests — the learner sees these before submitting."""

from solution import dedupe


def test_removes_duplicates_in_order():
    assert dedupe([1, 2, 1, 3, 2]) == [1, 2, 3]


def test_keeps_strings_in_order():
    assert dedupe(["b", "a", "b", "c", "a"]) == ["b", "a", "c"]


def test_empty_list_stays_empty():
    assert dedupe([]) == []


def test_returns_a_new_list():
    original = [1, 2, 1]
    result = dedupe(original)
    assert result == [1, 2]
    assert result is not original
