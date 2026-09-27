"""Visible tests — the learner sees these before submitting."""

from solution import batches, take


def test_batches_splits_into_full_batches():
    assert list(batches([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]


def test_batches_of_an_empty_iterable():
    assert list(batches([], 3)) == []


def test_batches_returns_lists():
    assert all(isinstance(batch, list) for batch in batches(range(6), 2))


def test_take_returns_at_most_n():
    assert list(take([1, 2, 3, 4], 2)) == [1, 2]
    assert list(take([1, 2], 5)) == [1, 2]
