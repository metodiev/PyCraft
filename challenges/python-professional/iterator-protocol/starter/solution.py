class StepRange:
    """Restartable iterable producing ``start, start + step, ...`` while in range."""

    def __init__(self, start, stop, step=1):
        # TODO: validate (ints only, step != 0) and store the three attributes.
        raise NotImplementedError("Complete the StepRange constructor")

    def __iter__(self):
        """Return a fresh iterator over the values."""
        raise NotImplementedError("Complete the StepRange __iter__ method")

    def __len__(self):
        """Return the exact number of values."""
        raise NotImplementedError("Complete the StepRange __len__ method")

    def __contains__(self, value):
        """Return True when ``value`` is one of the produced values."""
        raise NotImplementedError("Complete the StepRange __contains__ method")

    def __eq__(self, other):
        """Compare two StepRange objects by the sequence they produce."""
        raise NotImplementedError("Complete the StepRange __eq__ method")

    def __repr__(self):
        """Return ``StepRange(start, stop, step)``."""
        raise NotImplementedError("Complete the StepRange __repr__ method")


class Countdown:
    """Single-use iterator yielding ``start, start - 1, ..., 1``."""

    def __init__(self, start):
        # TODO: validate (non-negative int) and store the remaining count.
        raise NotImplementedError("Complete the Countdown constructor")

    def __iter__(self):
        """Return ``self`` — a Countdown is its own iterator."""
        raise NotImplementedError("Complete the Countdown __iter__ method")

    def __next__(self):
        """Return the next value or raise a bare ``StopIteration``."""
        raise NotImplementedError("Complete the Countdown __next__ method")
