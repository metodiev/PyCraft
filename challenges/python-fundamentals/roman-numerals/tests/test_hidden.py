"""Hidden tests — graded on Submit, never shown to the learner."""

import pytest

from solution import from_roman, to_roman


def test_full_range_round_trip():
    for number in range(1, 4000):
        text = to_roman(number)
        assert from_roman(text) == number


def test_non_canonical_forms_are_rejected():
    for bad in ["IIII", "IIV", "VV", "XXXX", "VX", "IC", "IL", "MMMM", "IXI", "CMC"]:
        with pytest.raises(ValueError):
            from_roman(bad)


def test_bad_input_types_and_formatting():
    for bad in ["", " ", "iv", "MCMXCIV ", " IV", "M1", "ABC", "Ⅳ"]:
        with pytest.raises(ValueError):
            from_roman(bad)
    for bad in [True, False, 1.0, "4", None]:
        with pytest.raises(ValueError):
            to_roman(bad)


def test_subtractive_symbols_are_used():
    assert to_roman(4) == "IV"
    assert to_roman(9) == "IX"
    assert to_roman(40) == "XL"
    assert to_roman(90) == "XC"
    assert to_roman(400) == "CD"
    assert to_roman(900) == "CM"
    assert to_roman(444) == "CDXLIV"
    assert to_roman(1990) == "MCMXC"


def test_boundaries():
    assert to_roman(1) == "I"
    assert to_roman(3999) == "MMMCMXCIX"
    assert from_roman("I") == 1
    assert from_roman("MMMCMXCIX") == 3999
    with pytest.raises(ValueError):
        to_roman(4000)


def test_encoder_output_is_always_canonical():
    for number in (2, 5, 10, 50, 100, 500, 1000, 3888):
        text = to_roman(number)
        assert text == to_roman(from_roman(text))
        assert text.isupper()
