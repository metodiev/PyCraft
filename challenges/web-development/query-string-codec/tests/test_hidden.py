"""Hidden tests — graded on Submit, never shown to the learner."""

import pytest

from solution import decode_query, encode_query


def test_duplicate_keys_are_preserved_in_order():
    assert decode_query("tag=a&tag=b&tag=a") == [("tag", "a"), ("tag", "b"), ("tag", "a")]


def test_plus_and_percent_plus_are_different():
    assert decode_query("q=a+b") == [("q", "a b")]
    assert decode_query("q=a%2Bb") == [("q", "a+b")]
    assert decode_query("q=%20") == [("q", " ")]


def test_unreserved_set_is_exactly_right():
    safe = "AZaz09-._~"
    assert encode_query([(safe, safe)]) == f"{safe}={safe}"
    assert encode_query([(" ", "!")]) == "%20=%21"
    assert encode_query([("a/b", "c?d")]) == "a%2Fb=c%3Fd"
    assert encode_query([("a=b", "c&d")]) == "a%3Db=c%26d"
    # uppercase hex only
    assert encode_query([(" ", "")]) == "%20="


def test_no_leading_question_mark_and_empty_parameters():
    assert decode_query("?a=1") == [("a", "1")]
    assert decode_query("?") == []
    assert decode_query("&") == []
    assert decode_query("a=1&") == [("a", "1")]
    assert decode_query("&&a=1&&") == [("a", "1")]
    assert decode_query("flag") == [("flag", "")]
    assert decode_query("a=1&flag&b=") == [("a", "1"), ("flag", ""), ("b", "")]


def test_malformed_escapes_raise_value_error():
    for bad in ["x=%zz", "x=%2", "x=%", "x=%g0", "%C3", "%FF", "a=%C3%28"]:
        with pytest.raises(ValueError):
            decode_query(bad)


def test_valid_utf8_multibyte_round_trips():
    pairs = [("name", "Ævar Örn"), ("emoji", "🧪"), ("path", "/a/b c")]
    assert decode_query(encode_query(pairs)) == pairs
    assert encode_query(pairs) == (
        "name=%C3%86var%20%C3%96rn&emoji=%F0%9F%A7%AA&path=%2Fa%2Fb%20c"
    )


def test_type_errors_and_exact_round_trip():
    with pytest.raises(TypeError):
        encode_query([("a", 1)])
    with pytest.raises(TypeError):
        encode_query([(1, "a")])
    query = "a=1&b=%20&c=%2B&d=&e=a%2Fb"
    assert encode_query(decode_query(query)) == query
