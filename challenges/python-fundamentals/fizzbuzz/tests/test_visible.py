"""Visible tests — the learner sees these before submitting."""

from solution import fizzbuzz


def test_first_five_values():
    assert fizzbuzz(5) == ["1", "2", "Fizz", "4", "Buzz"]


def test_fifteen_returns_fizzbuzz():
    assert fizzbuzz(15)[-1] == "FizzBuzz"


def test_every_element_is_a_string():
    assert all(isinstance(element, str) for element in fizzbuzz(20))


def test_length_matches_n():
    assert len(fizzbuzz(7)) == 7
