def batches(iterable, size):
    """Yield successive lists of up to ``size`` items from ``iterable``.

    ``size`` must be an int >= 1, otherwise ``ValueError`` is raised immediately
    (before the returned iterator is consumed). The source is consumed lazily,
    so infinite iterables are supported as long as the caller stops pulling.

    >>> list(batches([1, 2, 3, 4, 5], 2))
    [[1, 2], [3, 4], [5]]
    """
    # TODO: validate ``size`` eagerly, then return a generator that pulls one batch at a time.
    raise NotImplementedError("Complete the batches function")


def take(iterable, n):
    """Yield at most the first ``n`` items of ``iterable``.

    ``n <= 0`` yields nothing and pulls nothing from the source. When the source
    is longer than ``n`` the remaining items stay available to other consumers.

    >>> list(take([1, 2, 3, 4], 2))
    [1, 2]
    """
    # TODO: return a lazy iterator over the first ``n`` items that never over-pulls.
    raise NotImplementedError("Complete the take function")
