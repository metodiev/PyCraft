def to_roman(number: int) -> str:
    """Return the canonical Roman numeral for ``number`` (1..3999).

    Raises ``ValueError`` for booleans, non-integers and out-of-range values.

    >>> to_roman(944)
    'CMXLIV'
    """
    # TODO: greedily subtract the descending numeral table to build the string.
    raise NotImplementedError("Complete the to_roman function")


def from_roman(text: str) -> int:
    """Return the integer for a canonical Roman numeral.

    Only strings that ``to_roman`` could have produced are accepted; everything
    else raises ``ValueError``.

    >>> from_roman("MCMXCIV")
    1994
    """
    # TODO: decode the numerals, then reject anything that is not canonical.
    raise NotImplementedError("Complete the from_roman function")
