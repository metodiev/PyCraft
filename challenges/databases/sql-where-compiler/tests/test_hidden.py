"""Hidden tests — graded on Submit, never shown to the learner."""

import pytest

from solution import compile_where, select

ROWS = [
    {"id": 1, "name": "ada", "age": 36},
    {"id": 2, "name": "grace", "age": None},
    {"id": 3, "name": "linus", "age": 54},
    {"id": 4, "name": "ada", "age": 20},
]


def test_null_never_matches_a_comparison():
    assert select(ROWS, "age = 36") == [ROWS[0]]
    assert select(ROWS, "age != 36") == [ROWS[2], ROWS[3]]
    assert select(ROWS, "age > 0") == [ROWS[0], ROWS[2], ROWS[3]]
    assert select(ROWS, "age = NULL") == []


def test_missing_column_is_null():
    assert select(ROWS, "missing IS NULL") == ROWS
    assert select(ROWS, "missing = 1") == []
    assert select(ROWS, "missing != 1") == []


def test_not_with_null_stays_unknown():
    assert select(ROWS, "NOT (age > 40)") == [ROWS[0], ROWS[3]]
    assert select(ROWS, "NOT (age IS NULL)") == [ROWS[0], ROWS[2], ROWS[3]]
    assert select(ROWS, "NOT (missing = 1)") == []


def test_three_valued_or_and_and():
    # NULL OR TRUE -> TRUE, so every row matches
    assert select(ROWS, "age = 36 OR TRUE") == ROWS
    assert select(ROWS, "age > 40 OR age IS NULL") == [ROWS[1], ROWS[2]]
    # NULL AND FALSE -> FALSE
    assert select(ROWS, "age > 40 AND FALSE") == []
    assert select(ROWS, "age > 100 OR age = 20") == [ROWS[3]]


def test_strings_numbers_and_type_mixing():
    assert select(ROWS, "name = 'ada'") == [ROWS[0], ROWS[3]]
    assert select(ROWS, "name < 'grace'") == [ROWS[0], ROWS[3]]
    assert select(ROWS, "name != 36") == ROWS
    # int vs str: '=' and the ordering operators are never True, '!=' is True —
    # but a NULL column is unknown, so row 2 still does not match.
    assert select(ROWS, "age = 'x'") == []
    assert select(ROWS, "age != 'x'") == [ROWS[0], ROWS[2], ROWS[3]]


def test_parentheses_override_precedence():
    assert select(ROWS, "(name = 'ada' OR age > 50) AND id < 3") == [ROWS[0]]
    assert select(ROWS, "((id = 1))") == [ROWS[0]]


def test_operators_and_literals_are_parsed_in_full():
    assert select(ROWS, "age <= 36") == [ROWS[0], ROWS[3]]
    assert select(ROWS, "age >= 54") == [ROWS[2]]
    assert select(ROWS, "age <> 0") == [ROWS[0], ROWS[2], ROWS[3]]
    assert select(ROWS, "TRUE") == ROWS
    assert select(ROWS, "FALSE") == []
    assert select(ROWS, "id = 1 AND age = 36 AND name = 'ada'") == [ROWS[0]]


def test_syntax_errors_raise_value_error():
    for bad in [
        "",
        "age >",
        "= 5",
        "age 5",
        "age == 5",
        "name = 'ada",
        "age > 40 AND",
        "age > 40)",
        "(age > 40",
        "age > 40 extra",
        "age LIKE 5",
        "age = 40 AND OR id = 1",
    ]:
        with pytest.raises(ValueError):
            compile_where(bad)


def test_select_does_not_mutate_rows():
    rows = [dict(row) for row in ROWS]
    snapshot = [dict(row) for row in rows]
    select(rows, "age > 0")
    assert rows == snapshot
