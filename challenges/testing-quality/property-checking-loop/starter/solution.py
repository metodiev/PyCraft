class Report:
    """Outcome of a property check run."""

    def __init__(self, passed, trials_run, counterexample=None, error=None, seed=0):
        # TODO: store the attributes described in the task, make the report
        # immutable in practice and support equality.
        raise NotImplementedError("Complete the Report value object")

    def __bool__(self):
        """Return True exactly when the property held."""
        raise NotImplementedError("Complete the Report __bool__ method")


def check(prop, generate, trials=100, seed=0):
    """Run ``prop`` against ``trials`` candidates produced by ``generate(rng)``.

    ``generate`` receives a seeded ``random.Random`` so runs are reproducible.
    Returns a :class:`Report`; failing integer counterexamples are shrunk toward
    zero. Exceptions raised by ``prop`` count as failures and are reported as
    text in ``Report.error``.

    >>> report = check(lambda n: n <= 10, lambda rng: rng.randint(0, 1000), trials=50, seed=1)
    >>> report.passed
    False
    >>> report.counterexample
    11
    """
    # TODO: loop trials times, call prop on generated candidates, shrink integer
    # counterexamples and return a Report.
    raise NotImplementedError("Complete the check function")
