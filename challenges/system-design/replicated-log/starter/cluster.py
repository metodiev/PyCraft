"""Cluster-level orchestration: quorum, elections, partitions.

The safety property this file exists to enforce: **a group that does not hold a
majority of the cluster can never elect a leader or commit a write.**

Tests import ``Cluster``, ``majority``, ``PartitionError`` and ``Quorum`` here.
"""

from __future__ import annotations

from collections.abc import Iterable

from log import Entry
from node import Node


class PartitionError(RuntimeError):
    """Raised for an illegal partition request."""


def majority(size: int) -> int:
    """The smallest number of nodes that constitutes a majority of ``size``."""
    # TODO: implement.
    raise NotImplementedError


class Quorum:
    """A named group of node ids that can hold a majority."""

    def __init__(self, members: Iterable[str], total: int) -> None:
        self.members = frozenset(members)
        self.total = total

    @property
    def size(self) -> int:
        # TODO: implement.
        raise NotImplementedError

    @property
    def has_majority(self) -> bool:
        """Whether this group alone constitutes a majority of the cluster."""
        # TODO: implement.
        raise NotImplementedError


class Cluster:
    """A set of nodes with an explicit, testable partition model."""

    def __init__(self, members: Iterable[str]) -> None:
        self.nodes: dict[str, Node] = {member: Node(member) for member in members}
        self.leader: str | None = None
        self._groups: list[frozenset[str]] = [frozenset(self.nodes)]

    # --- membership ------------------------------------------------------
    @property
    def size(self) -> int:
        # TODO: implement.
        raise NotImplementedError

    def reachable_from(self, node_id: str) -> frozenset[str]:
        """Every node the given node can currently talk to, including itself."""
        # TODO: implement.
        raise NotImplementedError

    def partition(self, *groups: Iterable[str]) -> None:
        """Split the cluster into mutually unreachable groups.

        The groups must between them cover every node exactly once.
        """
        # TODO: implement, raising PartitionError on a bad split.
        raise NotImplementedError

    def heal(self) -> None:
        """Restore full connectivity, then repair divergent followers."""
        # TODO: implement. Repair must never rewrite a committed entry.
        raise NotImplementedError

    # --- elections -------------------------------------------------------
    def elect(self, candidate_id: str) -> str | None:
        """Run an election for ``candidate_id``.

        Returns the new leader, or ``None`` when the candidate cannot reach a
        majority of the *whole* cluster.
        """
        # TODO: implement. A unanimous minority must still fail.
        raise NotImplementedError

    # --- replication -----------------------------------------------------
    def append(self, value: str) -> int | None:
        """Append through the current leader.

        Returns the committed index, or ``None`` when no quorum was reachable.

        A write that does not reach a quorum must leave **no trace**: discard it
        rather than keeping it as an uncommitted tail, otherwise a later heal
        would replicate and commit a write the cluster had already rejected.
        """
        # TODO: implement. Commit only the index that a majority holds.
        raise NotImplementedError

    def committed_values(self) -> list[str]:
        """The values the cluster has committed, in log order.

        Defined by the leader's log; every follower must agree after a heal.
        """
        # TODO: implement.
        raise NotImplementedError

    def log_values(self, node_id: str) -> list[str]:
        """One node's entries, committed or not."""
        # TODO: implement.
        raise NotImplementedError
