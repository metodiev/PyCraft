"""Hidden tests — graded on Submit, never shown to the learner."""

import pytest

from solution import decode, encode


def test_case_sensitive_runs():
    assert encode("aA") == "aA"
    assert encode("aaaAAA") == "a3A3"
    assert decode("aA") == "aA"
    assert decode("a3A3") == "aaaAAA"


def test_single_character_runs_inside_a_longer_text():
    assert encode("abbbc") == "ab3c"
    assert encode("aabbaa") == "a2b2a2"
    assert decode("a1b2") == "abb"
    assert decode("ab2") == "abb"


def test_multi_digit_counts():
    assert decode("a12") == "a" * 12
    assert decode("z100") == "z" * 100
    assert encode("z" * 100) == "z100"
    assert decode("a10b10") == "a" * 10 + "b" * 10


def test_invalid_encodings_raise_value_error():
    for bad in ["12a", "a0", "a2-", "-a", "2", "a1!", "aa!", "a-1", " ", "a2b_"]:
        with pytest.raises(ValueError):
            decode(bad)


def test_encode_rejects_every_non_letter():
    for bad in ["a b", "a1", "!", "a\n", "café", "a\tb", "a-b"]:
        with pytest.raises(ValueError):
            encode(bad)
    assert encode("") == ""


def test_encode_produces_canonical_text():
    for text in ["a", "aa", "ab", "baaab", "A" * 30 + "b" + "C" * 3, "ab" * 20]:
        encoded = encode(text)
        assert decode(encoded) == text
        assert encode(decode(encoded)) == encoded


def test_round_trip_on_awkward_texts():
    for text in ["z", "zz", "za", "az", "aaabaa", "y" * 9 + "x"]:
        assert decode(encode(text)) == text
