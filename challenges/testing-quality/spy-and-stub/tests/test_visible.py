"""Visible tests — the learner sees these before submitting."""

import pytest

from solution import Spy


def test_records_calls():
    spy = Spy()
    spy(1, 2, key="value")
    assert spy.call_count == 1
    call = spy.calls[0]
    assert call.args == (1, 2)
    assert call.kwargs == {"key": "value"}


def test_returns_the_configured_value():
    spy = Spy()
    spy.return_value = 42
    assert spy() == 42


def test_delegates_to_the_target():
    spy = Spy(target=lambda a, b=0: a + b)
    assert spy(2, b=3) == 5
    spy.assert_called_once()
    spy.assert_called_with(2, b=3)


def test_assertions_raise():
    spy = Spy()
    with pytest.raises(AssertionError):
        spy.assert_called_once()
    spy()
    with pytest.raises(AssertionError):
        spy.assert_not_called()
