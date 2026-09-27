class Store:
    """MVCC key/value store with per-transaction snapshots."""

    def begin(self):
        """Start a transaction and return its monotonically increasing int id."""
        # TODO: allocate the next id, record the current commit counter and mark it active.
        raise NotImplementedError("Complete the Store.begin method")

    def write(self, tx, key, value):
        """Stage ``value`` for ``key`` in transaction ``tx``.

        Raises ``ValueError`` when ``tx`` is not active or when another active
        transaction already owns the key.
        """
        # TODO: stage the version and claim the key for this transaction.
        raise NotImplementedError("Complete the Store.write method")

    def read(self, tx, key):
        """Return the value visible to ``tx`` for ``key``, or ``None``."""
        # TODO: pick the newest visible version (committed before the snapshot, or owned by tx).
        raise NotImplementedError("Complete the Store.read method")

    def commit(self, tx):
        """Make ``tx``'s staged versions visible to later snapshots."""
        # TODO: bump the commit counter, publish the versions and release the keys.
        raise NotImplementedError("Complete the Store.commit method")

    def abort(self, tx):
        """Discard ``tx``'s staged versions."""
        # TODO: drop the staged versions and release the keys.
        raise NotImplementedError("Complete the Store.abort method")

    def status(self, tx):
        """Return ``"active"``, ``"committed"``, ``"aborted"`` or ``"unknown"``."""
        # TODO: report the transaction state without raising.
        raise NotImplementedError("Complete the Store.status method")
