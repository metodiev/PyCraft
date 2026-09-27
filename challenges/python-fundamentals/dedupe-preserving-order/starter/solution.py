def dedupe(items: list) -> list:
    """Return a new list with duplicates removed, keeping first-occurrence order.

    Equality is Python's ``==``. Elements may be unhashable (lists, dicts), so
    ``set()`` cannot be used blindly. ``items`` is never modified.

    >>> dedupe([1, 2, 1, 3, 2])
    [1, 2, 3]
    >>> dedupe([[1], [1], [2]])
    [[1], [2]]
    """
    # TODO: build a new list, appending an element only the first time it is seen.
    raise NotImplementedError("Complete the dedupe function")
