def atomic(store):
    """Return a context manager that rolls ``store`` back if the block raises.

    Mutations are live inside the block. If the block completes normally they
    are kept; if it raises, ``store`` is restored to its exact contents from
    ``with`` entry and the exception keeps propagating.

    >>> config = {"debug": False}
    >>> with atomic(config):
    ...     config["debug"] = True
    >>> config
    {'debug': True}
    """
    # TODO: snapshot the mapping, yield it, and restore on BaseException before re-raising.
    raise NotImplementedError("Complete the atomic context manager")
