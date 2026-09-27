"""Hidden tests — graded on Submit, never shown to the learner."""

import pytest

from solution import atomic


def test_added_keys_are_removed_on_failure():
    store = {"keep": 1}
    with pytest.raises(RuntimeError):
        with atomic(store):
            store["added"] = 2
            store["also"] = 3
            raise RuntimeError("nope")
    assert store == {"keep": 1}
    assert "added" not in store


def test_deleted_keys_come_back():
    store = {"a": 1, "b": 2, "c": 3}
    with pytest.raises(KeyError):
        with atomic(store):
            del store["b"]
            store.pop("c")
            raise KeyError("b")
    assert store == {"a": 1, "b": 2, "c": 3}


def test_same_exception_object_propagates():
    store: dict = {}
    error = ValueError("identity")
    with pytest.raises(ValueError) as excinfo:
        with atomic(store):
            store["x"] = 1
            raise error
    assert excinfo.value is error


def test_mutations_are_live_inside_the_block():
    store = {"a": 1}
    seen = []
    with atomic(store):
        store["b"] = 2
        seen.append(dict(store))
    assert seen == [{"a": 1, "b": 2}]
    assert store == {"a": 1, "b": 2}


def test_base_exceptions_roll_back_too():
    store = {"a": 1}
    with pytest.raises(SystemExit):
        with atomic(store):
            store["a"] = 2
            store["b"] = 3
            raise SystemExit(1)
    assert store == {"a": 1}


def test_nested_blocks_restore_their_own_snapshot():
    store = {"level": 0}
    with pytest.raises(RuntimeError):
        with atomic(store):
            store["level"] = 1
            store["outer"] = True
            with atomic(store):
                store["level"] = 2
                store["inner"] = True
            assert store == {"level": 2, "outer": True, "inner": True}
            raise RuntimeError("outer failed")
    assert store == {"level": 0}


def test_inner_failure_does_not_touch_outer_mutations():
    store = {"a": 1}
    with atomic(store):
        store["b"] = 2
        with pytest.raises(ValueError):
            with atomic(store):
                store["c"] = 3
                raise ValueError("inner")
        assert store == {"a": 1, "b": 2}
    assert store == {"a": 1, "b": 2}
