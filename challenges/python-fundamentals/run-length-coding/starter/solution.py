def encode(text: str) -> str:
    """Return the run-length encoding of ``text``.

    ``text`` must consist of ASCII letters; runs of length 1 are emitted as the
    bare character, longer runs as ``<char><count>``.

    >>> encode("aaabbc")
    'a3b2c'
    """
    # TODO: group consecutive equal characters and emit char + count (count only when > 1).
    raise NotImplementedError("Complete the encode function")


def decode(encoded: str) -> str:
    """Return the text described by the run-length encoded ``encoded``.

    Raises ``ValueError`` when ``encoded`` is not a sequence of ``letter`` or
    ``letter<count>`` items with ``count >= 1``.

    >>> decode("a3b2c")
    'aaabbc'
    """
    # TODO: validate the whole encoded string, then expand each run.
    raise NotImplementedError("Complete the decode function")
