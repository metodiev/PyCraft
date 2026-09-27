"""Hidden tests — graded on Submit, never shown to the learner."""

import itertools

import pytest

from solution import batches, take


class Counted:
    """Iterator that fails loudly if it is pulled more often than allowed."""

    def __init__(self, limit=1000):
        self.pulls = 0
        self.limit = limit

    def __iter__(self):
        return self

    def __next__(self):
        if self.pulls >= self.limit:
            raise AssertionError("source pulled too many times")
        self.pulls += 1
        return self.pulls


def test_invalid_size_raises_before_iteration():
    with pytest.raises(ValueError):
        batches([1, 2, 3], 0)
    with pytest.raises(ValueError):
        batches([1, 2, 3], -1)


def test_batches_pulls_exactly_one_batch():
    source = Counted()
    stream = batches(source, 3)
    assert next(stream) == [1, 2, 3]
    assert source.pulls == 3
    assert next(stream) == [4, 5, 6]
    assert source.pulls == 6


def test_batches_consumes_a_finite_source_exactly_once():
    pulled = []

    def source():
        for value in range(5):
            pulled.append(value)
            yield value

    assert list(batches(source(), 3)) == [[0, 1, 2], [3, 4]]
    assert pulled == [0, 1, 2, 3, 4]


def test_take_does_not_over_pull():
    source = Counted()
    assert list(take(source, 0)) == []
    assert source.pulls == 0
    assert list(take(source, 2)) == [1, 2]
    assert source.pulls == 2
    assert next(source) == 3


def test_take_leaves_the_rest_of_the_source_available():
    iterator = iter([1, 2, 3, 4, 5])
    assert list(take(iterator, 2)) == [1, 2]
    assert next(iterator) == 3


def test_batches_handles_a_long_iterable_stream():
    assert list(itertools.islice(batches(itertools.count(10), 3), 2)) == [
        [10, 11, 12],
        [13, 14, 15],
    ]


def test_laziness_of_batch_creation():
    created = []

    def tracker():
        for value in range(9):
            created.append(value)
            yield value

    stream = batches(tracker(), 3)
    assert created == []
    first = next(stream)
    assert first == [0, 1, 2]
    assert created == [0, 1, 2]
    assert list(stream) == [[3, 4, 5], [6, 7, 8]]


def test_exact_batch_boundaries():
    assert list(batches(range(4), 4)) == [[0, 1, 2, 3]]
    assert list(batches(range(4), 3)) == [[0, 1, 2], [3]]
    assert list(batches("abcd", 1)) == [["a"], ["b"], ["c"], ["d"]]
