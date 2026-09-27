"""Hidden tests — graded on Submit, never shown to the learner."""

import pytest

from solution import Call, Spy


class Boom(Exception):
    """Custom error used to prove exception handling."""


def test_calls_snapshot_cannot_be_mutated():
    spy = Spy()
    spy("one")
    snapshot = spy.calls
    snapshot.append("junk")
    snapshot.clear()
    assert spy.call_count == 1
    assert len(spy.calls) == 1
    assert spy.calls[0].args == ("one",)


def test_side_effect_handles_instances_and_classes():
    error = Boom("instance")
    spy = Spy()
    spy.side_effect = [error, Boom, "recovered"]
    with pytest.raises(Boom) as first:
        spy()
    assert first.value is error
    with pytest.raises(Boom):
        spy()
    assert spy() == "recovered"
    assert spy.call_count == 3


def test_side_effect_exhaustion_falls_back_to_target_and_return_value():
    spy = Spy(target=lambda: "from target")
    spy.side_effect = ["scripted"]
    assert spy() == "scripted"
    assert spy() == "from target"

    plain = Spy()
    plain.return_value = "configured"
    plain.side_effect = ["scripted"]
    assert plain() == "scripted"
    assert plain() == "configured"


def test_assert_called_with_matches_keywords_regardless_of_order():
    spy = Spy()
    spy(1, b=2, a=3)
    spy.assert_called_with(1, a=3, b=2)
    with pytest.raises(AssertionError):
        spy.assert_called_with(1, a=3)
    with pytest.raises(AssertionError):
        spy.assert_called_with(1, a=3, b=2, extra=None)


def test_assert_called_with_only_looks_at_the_last_call():
    spy = Spy()
    spy("first")
    spy("second", tag=True)
    spy.assert_called_with("second", tag=True)
    with pytest.raises(AssertionError):
        spy.assert_called_with("first")


def test_reset_keeps_configuration():
    spy = Spy(target=lambda: "from target")
    spy.return_value = "kept"
    spy.side_effect = ["scripted"]
    assert spy() == "scripted"          # scripted value wins
    spy.reset()
    assert spy.call_count == 0
    assert spy.calls == []
    assert spy() == "from target"       # configuration survived the reset
    spy.side_effect = ["again"]
    assert spy() == "again"
    assert spy() == "from target"


def test_call_equality_and_independent_kwargs():
    spy = Spy()
    mapping = {"seen": 1}
    spy(**mapping)
    call = spy.calls[0]
    assert call == Call((), {"seen": 1})
    assert call.kwargs is not mapping
    call.kwargs["seen"] = 2
    assert spy.calls[0].kwargs == {"seen": 1}
