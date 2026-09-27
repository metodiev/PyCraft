def parse_csv_line(line: str) -> list[str]:
    """Return the fields of a single CSV record.

    Fields are separated by ``,``; a field starting with ``"`` is quoted, and
    ``""`` inside a quoted field is a literal quote. Whitespace is preserved.
    Malformed input (stray quotes, an unterminated quoted field, or embedded
    newlines) raises ``ValueError``.

    >>> parse_csv_line('a,"b,c",d')
    ['a', 'b,c', 'd']
    >>> parse_csv_line('"a""b"')
    ['a"b']
    """
    # TODO: walk the line with an index, handling quoted and unquoted fields,
    # and raise ValueError for stray quotes, unterminated fields and newlines.
    raise NotImplementedError("Complete the parse_csv_line function")
