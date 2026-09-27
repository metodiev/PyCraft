"""Hidden tests — graded on Submit, never shown to the learner."""

from solution import fizzbuzz


def test_zero_returns_empty_list():
    assert fizzbuzz(0) == []


def test_negative_returns_empty_list():
    assert fizzbuzz(-7) == []


def test_one_is_a_single_plain_number():
    assert fizzbuzz(1) == ["1"]


def test_fifteen_boundaries():
    result = fizzbuzz(15)
    assert len(result) == 15
    assert result[2] == "Fizz"
    assert result[4] == "Buzz"
    assert result[8] == "Fizz"
    assert result[9] == "Buzz"
    assert result[0] == "1"
    assert result[14] == "FizzBuzz"


def test_multiples_of_both_are_fizzbuzz():
    result = fizzbuzz(45)
    for value in (15, 30, 45):
        assert result[value - 1] == "FizzBuzz"


def test_hundred_element_counts():
    result = fizzbuzz(100)
    assert len(result) == 100
    assert result.count("FizzBuzz") == 6
    assert result.count("Fizz") == 27
    assert result.count("Buzz") == 14
    assert result[-1] == "Buzz"
