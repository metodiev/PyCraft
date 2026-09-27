"""Visible tests — the learner sees these before submitting."""

import pytest

from solution import Store


def test_transaction_ids_increase():
    store = Store()
    first = store.begin()
    second = store.begin()
    assert isinstance(first, int) and isinstance(second, int)
    assert second > first


def test_own_writes_are_visible_immediately():
    store = Store()
    tx = store.begin()
    store.write(tx, "x", 1)
    assert store.read(tx, "x") == 1
    assert store.status(tx) == "active"


def test_commit_publishes_to_later_snapshots():
    store = Store()
    writer = store.begin()
    store.write(writer, "x", 42)
    store.commit(writer)
    assert store.status(writer) == "committed"
    assert store.read(store.begin(), "x") == 42


def test_uncommitted_writes_are_invisible_to_other_transactions():
    store = Store()
    writer = store.begin()
    store.write(writer, "x", 42)
    observer = store.begin()
    assert store.read(observer, "x") is None


def test_abort_discards_writes():
    store = Store()
    tx = store.begin()
    store.write(tx, "x", 1)
    store.abort(tx)
    assert store.status(tx) == "aborted"
    assert store.read(store.begin(), "x") is None
