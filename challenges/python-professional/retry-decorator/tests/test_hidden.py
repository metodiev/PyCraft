"""Hidden tests — graded on Submit, never shown to the learner."""

import pytest

from solution import retry


class CustomError(Exception):
    """Domain-specific error used to prove the exception filter is honoured."""


def test_default_times_is_three_attempts():
    calls = []

    @retry()
    def always_fails():
        calls.append(1)
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        always_fails()
    assert len(calls) == 3


def test_times_one_means_a_single_attempt():
    calls = []

    @retry(times=1)
    def one_shot():
        calls.append(1)
        raise ValueError("once")

    with pytest.raises(ValueError):
        one_shot()
    assert len(calls) == 1


def test_exhausting_attempts_re_raises_the_last_exception():
    seen = []

    @retry(times=4, exceptions=(CustomError,))
    def increasingly_specific():
        seen.append(len(seen) + 1)
        raise CustomError(f"attempt {len(seen)}")

    with pytest.raises(CustomError) as excinfo:
        increasingly_specific()

    assert len(seen) == 4
    assert str(excinfo.value) == "attempt 4"


def test_unrelated_exception_is_not_retried():
    calls = []

    @retry(times=3, exceptions=(CustomError,))
    def wrong_error():
        calls.append(1)
        raise ValueError("out of contract")

    with pytest.raises(ValueError):
        wrong_error()
    assert len(calls) == 1


def test_wraps_metadata_and_reports_wrapped_function():
    def documented(x):
        """Docstring that must survive decoration."""
        return x

    wrapped = retry(times=2)(documented)

    assert wrapped.__name__ == "documented"
    assert wrapped.__doc__ == "Docstring that must survive decoration."
    assert wrapped.__wrapped__ is documented


def test_eventual_success_returns_exact_value_and_stops_retrying():
    calls = []

    @retry(times=5, exceptions=(KeyError,))
    def eventually():
        calls.append(1)
        if len(calls) < 3:
            raise KeyError("missing")
        return {"answer": 42}

    assert eventually() == {"answer": 42}
    assert len(calls) == 3


def test_kwargs_and_args_are_forwarded_on_every_attempt():
    seen = []

    @retry(times=3, exceptions=(TypeError,))
    def collect(*args, **kwargs):
        seen.append((args, kwargs))
        if len(seen) < 3:
            raise TypeError("retry me")
        return args, kwargs

    result = collect(1, "two", key="value")
    assert result == ((1, "two"), {"key": "value"})
    assert seen == [((1, "two"), {"key": "value"})] * 3
