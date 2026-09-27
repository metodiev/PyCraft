def collatz_steps(n: int) -> int:
    """Return how many ``3n+1`` steps ``n`` needs to reach ``1``.

    ``n`` must be at least ``1``; anything smaller raises ``ValueError``.

    >>> collatz_steps(1)
    0
    >>> collatz_steps(6)
    8
    """
    # TODO: loop until n == 1, applying the even/odd rule and counting the steps.
    raise NotImplementedError("Complete the collatz_steps function")


def longest_chain(limit: int) -> int:
    """Return the smallest start in ``1..limit`` with the longest Collatz chain.

    ``limit`` must be at least ``1``; anything smaller raises ``ValueError``.
    Ties are broken by taking the smallest starting value.

    >>> longest_chain(10)
    9
    """
    # TODO: scan 1..limit, keeping the first start that reaches the highest step count.
    raise NotImplementedError("Complete the longest_chain function")
