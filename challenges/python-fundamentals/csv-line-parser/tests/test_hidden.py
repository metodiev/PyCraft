"""Hidden tests — graded on Submit, never shown to the learner."""

import pytest

from solution import parse_csv_line


def test_doubled_quotes_are_one_literal_quote():
    assert parse_csv_line('"a""b"') == ['a"b']
    assert parse_csv_line('"say ""hi""",x') == ['say "hi"', "x"]
    assert parse_csv_line('""') == [""]


def test_empty_fields_around_commas():
    assert parse_csv_line("a,") == ["a", ""]
    assert parse_csv_line(",a") == ["", "a"]
    assert parse_csv_line(",") == ["", ""]
    assert parse_csv_line(",,") == ["", "", ""]
    assert parse_csv_line('"a",') == ["a", ""]


def test_whitespace_is_preserved_and_not_trimmed():
    assert parse_csv_line(" a , b ") == [" a ", " b "]
    assert parse_csv_line('" a "') == [" a "]
    assert parse_csv_line("a, ,b") == ["a", " ", "b"]


def test_malformed_quotes_raise_value_error():
    for bad in ['"a', 'a"b', '"a"b', '"a""', 'a,"b"c', '"a"""b"', '"']:
        with pytest.raises(ValueError):
            parse_csv_line(bad)


def test_embedded_newlines_are_rejected():
    for bad in ["a\nb", "a\r\nb", '"a\nb"', "a\rb"]:
        with pytest.raises(ValueError):
            parse_csv_line(bad)


def test_quoted_fields_with_special_characters():
    assert parse_csv_line('"a,b""c,d",e') == ['a,b"c,d', "e"]
    assert parse_csv_line('"café, x",y') == ["café, x", "y"]
    assert parse_csv_line('",",","') == [",", ","]
