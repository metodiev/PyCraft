"""Hidden tests — graded on Submit, never shown to the learner."""

from solution import word_count


def test_punctuation_only_yields_empty_dict():
    assert word_count("!!! ... ---") == {}


def test_splits_on_every_non_alphanumeric_character():
    assert word_count("a,b;c!d?e") == {"a": 1, "b": 1, "c": 1, "d": 1, "e": 1}


def test_hyphenated_words_split_into_two():
    result = word_count("well-known state-of-the-art")
    assert result == {
        "well": 1,
        "known": 1,
        "state": 1,
        "of": 1,
        "the": 1,
        "art": 1,
    }


def test_unicode_letters_are_not_word_characters():
    assert word_count("café naïve Öl 中文") == {"caf": 1, "na": 1, "ve": 1, "l": 1}


def test_digits_count_as_words_and_underscores_split():
    assert word_count("a_b 2fa 2FA 42") == {"a": 1, "b": 1, "2fa": 2, "42": 1}


def test_mixed_case_and_repeated_tokens():
    text = "Repeat repeat REPEAT no no...  no"
    assert word_count(text) == {"repeat": 3, "no": 3}


def test_counts_are_positive_integers_only():
    result = word_count("x y y z z z")
    assert sorted(result) == ["x", "y", "z"]
    assert all(isinstance(count, int) and count > 0 for count in result.values())
    assert result["z"] == 3
