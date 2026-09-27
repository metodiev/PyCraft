"""One replica.

A node owns its term, the vote it has cast in that term, its log and its commit
index. The two safety rules it enforces are:

* at most **one vote per term**;
* an append from a **stale** leader (older term, or a prefix that does not
  match) is refused.

Tests import ``Node`` from here.
"""

from __future__ import annotations

from log import Entry, ReplicatedLog


class Node:
    """A single replica of the log."""

    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        self.term = 0
        self.voted_for: str | None = None
        self.log = ReplicatedLog()
        self.commit_index = 0
        self.leader_id: str | None = None

    # --- elections -------------------------------------------------------
    def grant_vote(self, candidate_id: str, term: int, last_index: int, last_term: int) -> bool:
        """Grant a vote, or refuse it.

        Refuse when the term is stale, when a vote was already cast in this
        term for someone else, or when the candidate's log is behind.
        """
        # TODO: implement. A higher term must clear the previous vote first.
        raise NotImplementedError

    # --- replication -----------------------------------------------------
    def handle_append(
        self,
        leader_term: int,
        prev_index: int,
        prev_term: int,
        entries: list[Entry],
        *,
        leader_id: str | None = None,
    ) -> bool:
        """Accept a replication request from a leader.

        Refuse a stale term, or a request whose ``prev_index``/``prev_term`` do
        not match this log — the follower must ask the leader to back up
        instead of guessing.

        On acceptance, drop any conflicting suffix **before** appending: the
        log must never hold two different entries at the same index.
        """
        # TODO: implement.
        raise NotImplementedError

    def advance_commit(self, index: int) -> None:
        """Advance this node's commit index, never beyond what it holds."""
        # TODO: implement.
        raise NotImplementedError

    # --- crash -----------------------------------------------------------
    def restart(self) -> None:
        """Lose volatile state, keep durable state.

        The term and the vote are *volatile*; the log is *not*. That asymmetry
        is what makes reusing a vote after a crash safe.
        """
        # TODO: implement.
        raise NotImplementedError
