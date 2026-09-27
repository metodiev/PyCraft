"""Visible tests — the learner sees these before submitting."""

import pytest

from solution import decode, encode


def test_encodes_short_text():
    assert encode("aaabbc") == "a3b2c"
    assert encode("aabb") == "a2b2"


def test_single_characters_are_not_numbered():
    assert encode("abc") == "abc"
    assert encode("") == ""


def test_decodes_back():
    assert decode("a3b2c") == "aaabbc"
    assert decode("a2b2") == "aabb"


def test_round_trip():
    text = "aaabbcddddd"
    assert decode(encode(text)) == text


def test_non_letters_are_rejected():
    with pytest.raises(ValueError):
        encode("a b")
