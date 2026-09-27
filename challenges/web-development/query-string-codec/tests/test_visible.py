"""Visible tests — the learner sees these before submitting."""

import pytest

from solution import decode_query, encode_query


def test_encodes_simple_pairs():
    assert encode_query([("a", "1")]) == "a=1"
    assert encode_query([("a", "1"), ("b", "2")]) == "a=1&b=2"
    assert encode_query([]) == ""


def test_escapes_spaces_and_plus():
    assert encode_query([("a b", "c d")]) == "a%20b=c%20d"
    assert encode_query([("q", "a+b")]) == "q=a%2Bb"


def test_decodes_simple_pairs():
    assert decode_query("a=1&b=2") == [("a", "1"), ("b", "2")]
    assert decode_query("q=a+b") == [("q", "a b")]
    assert decode_query("") == []


def test_decodes_and_encodes_utf8():
    assert encode_query([("x", "é")]) == "x=%C3%A9"
    assert decode_query("x=%C3%A9") == [("x", "é")]
