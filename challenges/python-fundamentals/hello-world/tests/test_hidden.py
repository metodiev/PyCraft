"""Hidden tests — graded on Submit, never shown to the learner."""

from solution import greet


def test_empty_name():
    assert greet("") == "Hello, !"


def test_unicode_name():
    assert greet("Åsa") == "Hello, Åsa!"


def test_name_with_spaces():
    assert greet("Grace Hopper") == "Hello, Grace Hopper!"


def test_exact_formatting():
    result = greet("World")
    assert result.startswith("Hello, ")
    assert result.endswith("!")
    assert result == "Hello, World!"


def test_is_stable():
    """Repeated calls with the same input must return the same value."""
    assert greet("World") == greet("World")
