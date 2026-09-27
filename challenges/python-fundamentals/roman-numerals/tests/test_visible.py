"""Visible tests — the learner sees these before submitting."""

import pytest

from solution import from_roman, to_roman


def test_encodes_basic_values():
    assert to_roman(1) == "I"
    assert to_roman(4) == "IV"
    assert to_roman(9) == "IX"
    assert to_roman(40) == "XL"
    assert to_roman(944) == "CMXLIV"
    assert to_roman(3999) == "MMMCMXCIX"


def test_decodes_basic_values():
    assert from_roman("IV") == 4
    assert from_roman("MCMXCIV") == 1994
    assert from_roman("I") == 1


def test_round_trip():
    for number in (1, 3, 58, 1994, 2024, 3999):
        assert from_roman(to_roman(number)) == number


def test_invalid_numbers_raise():
    for bad in (0, -1, 4000):
        with pytest.raises(ValueError):
            to_roman(bad)
