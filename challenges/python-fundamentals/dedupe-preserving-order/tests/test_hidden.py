"""Hidden tests — graded on Submit, never shown to the learner."""

from solution import dedupe


def test_all_duplicates_collapses_to_one():
    assert dedupe([7, 7, 7, 7]) == [7]


def test_no_duplicates_is_unchanged():
    assert dedupe([3, 1, 2]) == [3, 1, 2]


def test_unhashable_elements_do_not_crash():
    result = dedupe([[1], [1], [2], {"a": 1}, {"a": 1}, [2]])
    assert result == [[1], [2], {"a": 1}]


def test_mixed_types_use_equality():
    # ``True == 1`` and ``2 == 2.0``, while ``"1"``/``"2"`` are distinct values.
    assert dedupe([1, "1", True, 2.0, "2", 2]) == [1, "1", 2.0, "2"]


def test_original_list_is_not_mutated():
    original = [1, [2], 1, [2], 3]
    snapshot = list(original)
    result = dedupe(original)
    assert original == snapshot
    assert len(original) == 5
    assert result == [1, [2], 3]


def test_first_occurrence_object_is_kept():
    first = {"k": 1}
    duplicate = {"k": 1}
    assert dedupe([first, duplicate])[0] is first


def test_keeps_relative_order_of_unseen_values():
    assert dedupe([5, 5, 1, 5, 9, 1, 0]) == [5, 1, 9, 0]
