"""Visible tests — the learner sees these before submitting."""

import pytest

from solution import compile_where, select

ROWS = [
    {"id": 1, "name": "ada", "age": 36},
    {"id": 2, "name": "grace", "age": None},
    {"id": 3, "name": "linus", "age": 54},
]


def test_simple_comparison():
    assert select(ROWS, "age > 40") == [ROWS[2]]
    assert select(ROWS, "name = 'ada'") == [ROWS[0]]


def test_and_binds_tighter_than_or():
    assert select(ROWS, "name = 'ada' OR age > 50 AND id = 3") == [ROWS[0], ROWS[2]]
    assert select(ROWS, "name = 'ada' OR id = 3 AND age > 100") == [ROWS[0]]


def test_is_null():
    assert select(ROWS, "age IS NULL") == [ROWS[1]]
    assert select(ROWS, "age IS NOT NULL") == [ROWS[0], ROWS[2]]


def test_predicate_is_reusable():
    predicate = compile_where("id >= 2")
    assert predicate(ROWS[0]) is False
    assert predicate(ROWS[1]) is True
    assert predicate(ROWS[2]) is True
