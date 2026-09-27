def detect_flaky(history):
    """Return a report about flaky tests found in ``history``.

    ``history`` is a list of runs, each mapping a test id to ``"passed"``,
    ``"failed"`` or ``"skipped"``. A test is flaky when it both passed and failed
    at least once; skipped or absent runs are ignored entirely.

    >>> detect_flaky([{"a": "passed"}, {"a": "failed"}])
    {'a': {'outcomes': {'passed': 1, 'failed': 1}, 'flips': 1, 'first_flip_run': 1}}
    """
    # TODO: build a per-test timeline of executed outcomes, then report the tests
    # that both passed and failed.
    raise NotImplementedError("Complete the detect_flaky function")
