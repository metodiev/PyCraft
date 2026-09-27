def compile_where(clause: str):
    """Compile a restricted SQL ``WHERE`` clause into ``predicate(row) -> bool``.

    Supports comparisons with ``= != < <= > >=``, ``IS NULL`` / ``IS NOT NULL``,
    ``AND``/``OR``/``NOT``, parentheses and three-valued logic. Syntax errors
    raise ``ValueError``.

    >>> predicate = compile_where("age > 40")
    >>> predicate({"age": 54})
    True
    >>> predicate({"age": None})
    False
    """
    # TODO: tokenise, parse with AND binding tighter than OR, and return a callable
    # implementing three-valued logic.
    raise NotImplementedError("Complete the compile_where function")


def select(rows, clause: str):
    """Return the rows matching ``clause``, in order, without mutating them.

    >>> select([{"age": 54}, {"age": None}], "age IS NULL")
    [{'age': None}]
    """
    # TODO: compile the clause and filter the rows, keeping order.
    raise NotImplementedError("Complete the select function")
