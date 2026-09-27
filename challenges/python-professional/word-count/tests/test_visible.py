"""Visible tests — the learner sees these before submitting."""

from solution import word_count


def test_counts_simple_sentence():
    assert word_count("hello world") == {"hello": 1, "world": 1}


def test_counts_repeated_words():
    assert word_count("one two one") == {"one": 2, "two": 1}


def test_folds_case():
    assert word_count("The the THE") == {"the": 3}


def test_empty_text_gives_empty_dict():
    assert word_count("") == {}
