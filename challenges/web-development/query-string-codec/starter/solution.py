def encode_query(pairs):
    """Return a query string (no leading ``?``) for ``pairs``.

    Spaces and reserved characters are percent-encoded with uppercase hex; only
    ``A-Z a-z 0-9 - . _ ~`` stay literal. Non-string keys or values raise
    ``TypeError``.

    >>> encode_query([("a b", "c+d")])
    'a%20b=c%2Bd'
    """
    # TODO: percent-encode each key/value from its UTF-8 bytes and join with '&'.
    raise NotImplementedError("Complete the encode_query function")


def decode_query(query):
    """Return the ``(key, value)`` pairs of ``query`` in order, duplicates kept.

    ``+`` means space, ``%XX`` is a byte, and a parameter without ``=`` has an
    empty value. Malformed escapes raise ``ValueError``.

    >>> decode_query("a=1&a=2")
    [('a', '1'), ('a', '2')]
    """
    # TODO: split on '&', partition each part on '=', and percent-decode the halves.
    raise NotImplementedError("Complete the decode_query function")
