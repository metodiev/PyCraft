"""Visible tests — the learner sees these before submitting."""

from solution import greet


def test_greets_world():
    assert greet("World") == "Hello, World!"


def test_greets_a_person():
    assert greet("Ada") == "Hello, Ada!"


def test_returns_a_string():
    assert isinstance(greet("World"), str)
