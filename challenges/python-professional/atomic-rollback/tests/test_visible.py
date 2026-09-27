"""Visible tests — the learner sees these before submitting."""

import pytest

from solution import atomic


def test_mutations_are_kept_on_success():
    store = {"a": 1}
    with atomic(store):
        store["b"] = 2
    assert store == {"a": 1, "b": 2}


def test_changed_value_is_restored_on_failure():
    store = {"a": 1}
    with pytest.raises(RuntimeError, match="bad"):
        with atomic(store):
            store["a"] = 99
            raise RuntimeError("bad")
    assert store == {"a": 1}


def test_restores_the_same_mapping_object():
    store = {"a": 1}
    with pytest.raises(ValueError):
        with atomic(store):
            store["a"] = 2
            raise ValueError("boom")
    assert isinstance(store, dict)
    assert store == {"a": 1}


def test_can_be_used_again_after_success():
    store = {}
    with atomic(store):
        store["first"] = 1
    with atomic(store):
        store["second"] = 2
    assert store == {"first": 1, "second": 2}
