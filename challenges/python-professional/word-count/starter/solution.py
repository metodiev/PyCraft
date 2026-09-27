import re

_WORD_RE = re.compile(r"[a-zA-Z0-9]+")


def word_count(text: str) -> dict[str, int]:
    """Count case-insensitive ASCII-alphanumeric words in ``text``.

    A word is a maximal run of ``a-z``/``A-Z``/``0-9``. Every other character
    (including ``_``, ``-``, ``'`` and non-ASCII letters) acts as a separator.
    Words are lowercased before counting.

    >>> word_count("The the THE")
    {'the': 3}
    >>> word_count("well-known")
    {'well': 1, 'known': 1}
    """
    # TODO: extract ASCII-alphanumeric runs, lowercase them, and tally the counts.
    raise NotImplementedError("Complete the word_count function")
