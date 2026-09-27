import functools


def retry(times: int = 3, exceptions: tuple = (Exception,)):
    """Return a decorator that retries the wrapped function up to ``times`` attempts.

    The decorated function is called at most ``times`` times in total (so
    ``times=1`` means a single attempt). Only exceptions that are instances of
    the types in ``exceptions`` trigger another attempt; anything else
    propagates immediately. If every attempt fails, the last matching exception
    is re-raised. The wrapper preserves the wrapped function's metadata via
    ``functools.wraps`` and forwards all positional and keyword arguments.

    Usage::

        @retry(times=5, exceptions=(TimeoutError, ConnectionError))
        def call_api(url):
            ...

    >>> def flaky():
    ...     return "ok"
    >>> retry(times=3)(flaky)() == "ok"
    True
    """
    # TODO: return a decorator whose wrapper loops up to ``times`` attempts,
    # returning early on success and re-raising the last matching exception.
    raise NotImplementedError("Complete the retry decorator factory")
