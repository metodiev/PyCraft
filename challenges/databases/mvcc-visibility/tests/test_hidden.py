"""Hidden tests — graded on Submit, never shown to the learner."""

import pytest

from solution import Store


def test_second_writer_raises_until_the_first_finishes():
    store = Store()
    alice = store.begin()
    bob = store.begin()
    store.write(alice, "x", 1)
    with pytest.raises(ValueError):
        store.write(bob, "x", 2)
    store.commit(alice)
    store.write(bob, "x", 2)          # the key is free again
    assert store.read(bob, "x") == 2


def test_first_writer_wins_without_losing_updates():
    store = Store()
    seed = store.begin()
    store.write(seed, "counter", 1)
    store.commit(seed)

    alice = store.begin()
    bob = store.begin()
    store.write(alice, "counter", store.read(alice, "counter") + 1)
    # bob cannot re-stage the row while alice holds it: the update is not lost.
    with pytest.raises(ValueError):
        store.write(bob, "counter", store.read(bob, "counter") + 1)
    store.commit(alice)
    assert store.read(store.begin(), "counter") == 2
    # once alice is done, bob may write again
    store.write(bob, "counter", 99)
    store.commit(bob)
    assert store.read(store.begin(), "counter") == 99


def test_snapshot_isolation_for_readers():
    store = Store()
    seed = store.begin()
    store.write(seed, "x", "v1")
    store.commit(seed)

    reader = store.begin()
    writer = store.begin()
    store.write(writer, "x", "v2")
    assert store.read(writer, "x") == "v2"     # writer sees its own uncommitted work
    assert store.read(reader, "x") == "v1"     # reader's snapshot predates it
    store.commit(writer)
    assert store.read(reader, "x") == "v1"     # still its own snapshot
    assert store.read(store.begin(), "x") == "v2"


def test_abort_does_not_publish_and_keeps_the_previous_value():
    store = Store()
    seed = store.begin()
    store.write(seed, "x", "old")
    store.commit(seed)

    tx = store.begin()
    store.write(tx, "x", "new")
    store.abort(tx)
    assert store.read(store.begin(), "x") == "old"


def test_unknown_and_finished_transactions():
    store = Store()
    tx = store.begin()
    assert store.status(999) == "unknown"
    assert store.status("nope") == "unknown"
    with pytest.raises(ValueError):
        store.read(999, "x")
    with pytest.raises(ValueError):
        store.write(999, "x", 1)
    store.commit(tx)
    assert store.status(tx) == "committed"
    with pytest.raises(ValueError):
        store.read(tx, "x")
    with pytest.raises(ValueError):
        store.write(tx, "x", 1)
    with pytest.raises(ValueError):
        store.commit(tx)
    with pytest.raises(ValueError):
        store.abort(tx)


def test_own_uncommitted_write_beats_newer_committed_versions():
    store = Store()
    later = store.begin()
    store.write(later, "x", "committed")
    store.commit(later)

    tx = store.begin()
    store.write(tx, "x", "mine")
    assert store.read(tx, "x") == "mine"
    other = store.begin()
    assert store.read(other, "x") == "committed"


def test_interleaved_commits_are_seen_by_the_right_snapshots():
    store = Store()
    first = store.begin()
    store.write(first, "x", 1)
    before = store.begin()
    store.commit(first)
    after = store.begin()
    second = store.begin()
    store.write(second, "x", 2)
    store.commit(second)

    assert store.read(before, "x") is None
    assert store.read(after, "x") == 1
    assert store.read(store.begin(), "x") == 2


def test_keys_are_independent():
    store = Store()
    alice = store.begin()
    bob = store.begin()
    store.write(alice, "a", 1)
    store.write(bob, "b", 2)          # different key: no conflict
    store.commit(alice)
    store.commit(bob)
    fresh = store.begin()
    assert store.read(fresh, "a") == 1
    assert store.read(fresh, "b") == 2
    assert store.read(fresh, "missing") is None
