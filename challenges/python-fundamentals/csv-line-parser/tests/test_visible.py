"""Visible tests — the learner sees these before submitting."""

from solution import parse_csv_line


def test_splits_on_commas():
    assert parse_csv_line("a,b,c") == ["a", "b", "c"]


def test_empty_line_is_one_empty_field():
    assert parse_csv_line("") == [""]


def test_quoted_field_may_contain_a_comma():
    assert parse_csv_line('a,"b,c",d') == ["a", "b,c", "d"]


def test_simple_quoting_is_unwrapped():
    assert parse_csv_line('"a",b') == ["a", "b"]
