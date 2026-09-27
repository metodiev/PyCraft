"""Hidden tests — the safety properties that make a replicated log correct."""

import pytest

from cluster import Cluster, PartitionError, Quorum, majority
from log import Entry, LogError, ReplicatedLog
from node import Node


def build(cluster, leader="n1", values=("a", "b", "c")):
    """Elect a leader and commit a few values."""
    cluster.elect(leader)
    for value in values:
        cluster.append(value)
    return cluster


# --- quorum arithmetic ----------------------------------------------------
def test_majority_of_small_clusters():
    assert majority(1) == 1
    assert majority(2) == 2
    assert majority(4) == 3
    assert majority(5) == 3


def test_majority_is_strictly_more_than_half():
    """Two disjoint groups must never both hold a majority."""
    for size in range(1, 12):
        assert majority(size) > size / 2
        assert (size - majority(size)) < majority(size)


def test_a_half_in_a_four_node_cluster_is_not_a_majority():
    assert Quorum(["n1", "n2"], total=4).has_majority is False


def test_exactly_half_is_never_enough():
    for size in (2, 4, 6, 8):
        assert Quorum([f"n{index}" for index in range(size // 2)], total=size).has_majority is False


# --- log safety -----------------------------------------------------------
def test_a_decreasing_term_is_rejected():
    """Terms only move forwards; accepting a lower one rewrites history."""
    log = ReplicatedLog()
    log.append(Entry(term=5, index=1, value="a"))

    with pytest.raises(LogError):
        log.append(Entry(term=3, index=2, value="b"))


def test_a_committed_entry_cannot_be_truncated():
    """The single most important invariant in the whole project."""
    log = ReplicatedLog()
    for index in (1, 2, 3):
        log.append(Entry(term=1, index=index, value=f"v{index}"))
    log.commit(2)

    with pytest.raises(LogError):
        log.truncate_from(2)

    assert log.last_index == 3


def test_truncating_committed_entries_leaves_the_log_intact():
    log = ReplicatedLog()
    for index in (1, 2, 3):
        log.append(Entry(term=1, index=index, value=f"v{index}"))
    log.commit(3)

    with pytest.raises(LogError):
        log.truncate_from(1)

    assert [entry.value for entry in log.committed] == ["v1", "v2", "v3"]


def test_committing_beyond_the_log_is_rejected():
    log = ReplicatedLog()
    log.append(Entry(term=1, index=1, value="a"))

    with pytest.raises(LogError):
        log.commit(5)


def test_the_commit_index_never_exceeds_the_log():
    log = ReplicatedLog()
    log.append(Entry(term=1, index=1, value="a"))
    log.append(Entry(term=1, index=2, value="b"))
    log.commit(2)

    assert log.commit_index <= log.last_index


def test_entries_property_does_not_expose_the_internal_list():
    """Mutating the returned list must not change the log."""
    log = ReplicatedLog()
    log.append(Entry(term=1, index=1, value="a"))

    log.entries.append(Entry(term=1, index=2, value="injected"))

    assert log.last_index == 1


def test_is_up_to_date_compares_term_before_index():
    """A higher term wins even with a shorter log; index alone is not enough."""
    log = ReplicatedLog()
    log.append(Entry(term=2, index=1, value="a"))
    log.append(Entry(term=2, index=2, value="b"))

    # Longer log, older term: not up to date.
    assert log.is_up_to_date(term=1, index=99) is False
    # Shorter log, newer term: up to date.
    assert log.is_up_to_date(term=3, index=1) is True


def test_an_equal_term_with_a_shorter_index_is_not_up_to_date():
    log = ReplicatedLog()
    log.append(Entry(term=2, index=1, value="a"))
    log.append(Entry(term=2, index=2, value="b"))

    assert log.is_up_to_date(term=2, index=1) is False


def test_an_equal_term_and_index_is_up_to_date():
    log = ReplicatedLog()
    log.append(Entry(term=2, index=1, value="a"))
    log.append(Entry(term=2, index=2, value="b"))

    assert log.is_up_to_date(term=2, index=2) is True


def test_an_empty_log_defers_to_any_candidate():
    assert ReplicatedLog().is_up_to_date(term=1, index=0) is True


# --- voting ---------------------------------------------------------------
def test_a_candidate_with_a_stale_log_is_refused():
    """The vote that elects a stale leader is the vote that loses data."""
    node = Node("n1")
    node.handle_append(2, 0, 0, [Entry(2, 1, "a"), Entry(2, 2, "b")])

    assert node.grant_vote("n2", term=3, last_index=1, last_term=1) is False


def test_a_candidate_with_a_newer_term_and_shorter_log_is_accepted():
    node = Node("n1")
    node.handle_append(2, 0, 0, [Entry(2, 1, "a"), Entry(2, 2, "b")])

    assert node.grant_vote("n2", term=3, last_index=1, last_term=3) is True


def test_a_new_term_clears_the_previous_vote():
    node = Node("n1")
    node.grant_vote("n2", term=1, last_index=0, last_term=0)

    assert node.grant_vote("n3", term=2, last_index=0, last_term=0) is True
    assert node.voted_for == "n3"


def test_the_same_candidate_may_be_voted_for_again_in_a_new_term():
    node = Node("n1")
    node.grant_vote("n2", term=1, last_index=0, last_term=0)

    assert node.grant_vote("n2", term=2, last_index=0, last_term=0) is True


def test_a_vote_is_granted_again_after_a_restart_loses_the_term():
    """The term and the vote are volatile: a crash forgets both."""
    node = Node("n1")
    node.grant_vote("n2", term=5, last_index=0, last_term=0)

    node.restart()

    assert node.grant_vote("n3", term=1, last_index=0, last_term=0) is True
    assert node.voted_for == "n3"
    assert node.term == 1


def test_a_refused_vote_does_not_change_voted_for():
    node = Node("n1")
    node.handle_append(3, 0, 0, [Entry(3, 1, "a")])

    # Term 2 is stale for a node that has already seen term 3.
    assert node.grant_vote("n2", term=2, last_index=9, last_term=2) is False

    assert node.voted_for is None


# --- replication ----------------------------------------------------------
def test_a_matching_prefix_is_required():
    node = Node("n1")
    node.handle_append(1, 0, 0, [Entry(1, 1, "a")])

    # prev_index 5 does not exist here, so the leader must back up.
    assert node.handle_append(1, 5, 1, [Entry(1, 6, "b")]) is False
    assert node.log.last_index == 1


def test_a_conflicting_suffix_is_replaced():
    """The follower must not hold two different entries at one index."""
    node = Node("n1")
    node.handle_append(1, 0, 0, [Entry(1, 1, "a"), Entry(1, 2, "old")])

    assert node.handle_append(2, 1, 1, [Entry(2, 2, "new")]) is True

    assert node.log.get(2).value == "new"
    assert node.log.last_index == 2


def test_a_conflicting_suffix_is_truncated_not_appended():
    node = Node("n1")
    node.handle_append(1, 0, 0, [Entry(1, 1, "a"), Entry(1, 2, "old"), Entry(1, 3, "older")])

    node.handle_append(2, 1, 1, [Entry(2, 2, "new")])

    assert node.log.last_index == 2
    assert [entry.value for entry in node.log.entries] == ["a", "new"]


def test_a_stale_leader_cannot_overwrite_a_newer_log():
    node = Node("n1")
    node.handle_append(5, 0, 0, [Entry(5, 1, "committed-by-newer-term")])

    assert node.handle_append(4, 1, 4, [Entry(4, 2, "stale")]) is False
    assert node.log.get(1).value == "committed-by-newer-term"


def test_advancing_commit_never_exceeds_the_local_log():
    node = Node("n1")
    node.handle_append(1, 0, 0, [Entry(1, 1, "a")])

    node.advance_commit(10)

    assert node.commit_index == 1


def test_a_follower_does_not_commit_on_append_alone():
    """Commit follows from a majority, not from having received an entry."""
    node = Node("n1")

    node.handle_append(1, 0, 0, [Entry(1, 1, "a")])

    assert node.commit_index == 0


# --- cluster: elections ---------------------------------------------------
def test_a_unanimous_minority_still_cannot_elect():
    """Counting only reachable nodes is not enough; the group must be a majority."""
    cluster = Cluster(["n1", "n2", "n3", "n4", "n5"])
    cluster.partition({"n1", "n2"}, {"n3", "n4", "n5"})

    assert cluster.elect("n1") is None
    assert cluster.elect("n2") is None


def test_a_majority_group_can_elect():
    cluster = Cluster(["n1", "n2", "n3", "n4", "n5"])
    cluster.partition({"n1", "n2", "n3"}, {"n4", "n5"})

    assert cluster.elect("n1") == "n1"


def test_electing_an_unknown_node_raises():
    cluster = Cluster(["n1", "n2", "n3"])

    with pytest.raises(KeyError):
        cluster.elect("ghost")


def test_a_partitioning_that_drops_a_node_is_rejected():
    cluster = Cluster(["n1", "n2", "n3"])

    with pytest.raises(PartitionError):
        cluster.partition({"n1"}, {"n2"})


def test_a_partitioning_that_repeats_a_node_is_rejected():
    cluster = Cluster(["n1", "n2", "n3"])

    with pytest.raises(PartitionError):
        cluster.partition({"n1", "n2"}, {"n2", "n3"})


def test_reachable_from_is_symmetric():
    cluster = Cluster(["n1", "n2", "n3"])
    cluster.partition({"n1", "n2"}, {"n3"})

    assert cluster.reachable_from("n1") == cluster.reachable_from("n2")
    assert "n3" not in cluster.reachable_from("n1")
    assert "n1" not in cluster.reachable_from("n3")


# --- cluster: safety of committed data ------------------------------------
def test_committed_values_survive_a_minority_partition():
    cluster = build(Cluster(["n1", "n2", "n3"]), values=("a", "b"))
    cluster.partition({"n1"}, {"n2", "n3"})

    cluster.append("lost")

    cluster.heal()
    assert cluster.committed_values() == ["a", "b"]


def test_a_write_to_a_minority_leader_is_not_committed():
    cluster = build(Cluster(["n1", "n2", "n3"]), values=("a",))
    cluster.partition({"n1"}, {"n2", "n3"})

    assert cluster.append("rejected") is None
    assert cluster.committed_values() == ["a"]


def test_all_nodes_converge_after_a_heal():
    cluster = build(Cluster(["n1", "n2", "n3"]), values=("a", "b", "c"))
    cluster.partition({"n1"}, {"n2", "n3"})
    cluster.append("lost")
    cluster.heal()

    logs = [cluster.log_values(node) for node in ("n1", "n2", "n3")]

    assert logs[0] == logs[1] == logs[2]


def test_a_follower_recovers_entries_missed_while_partitioned():
    cluster = build(Cluster(["n1", "n2", "n3"]), values=("a",))
    cluster.partition({"n1", "n2"}, {"n3"})
    cluster.append("b")
    cluster.append("c")

    cluster.heal()

    assert cluster.log_values("n3") == ["a", "b", "c"]


def test_a_committed_entry_is_never_overwritten_by_a_heal():
    cluster = build(Cluster(["n1", "n2", "n3"]), values=("important",))
    cluster.partition({"n1"}, {"n2", "n3"})
    # The isolated node tries to write; it cannot commit.
    cluster.append("shadow")
    cluster.heal()

    assert cluster.committed_values() == ["important"]


def test_committed_values_are_in_log_order():
    cluster = build(Cluster(["n1", "n2", "n3"]), values=("first", "second", "third"))

    assert cluster.committed_values() == ["first", "second", "third"]


def test_commit_index_advances_one_entry_at_a_time():
    cluster = Cluster(["n1", "n2", "n3"])
    cluster.elect("n1")

    assert cluster.append("a") == 1
    assert cluster.append("b") == 2
    assert cluster.append("c") == 3


def test_a_larger_cluster_still_requires_a_majority():
    cluster = build(Cluster(["n1", "n2", "n3", "n4", "n5"]), values=("a",))
    cluster.partition({"n1", "n2"}, {"n3", "n4", "n5"})

    assert cluster.append("lost") is None

    cluster.heal()
    assert cluster.committed_values() == ["a"]


def test_appending_without_a_leader_is_refused():
    cluster = Cluster(["n1", "n2", "n3"])

    assert cluster.append("orphan") is None
    assert cluster.committed_values() == []


def test_the_cluster_recovers_after_a_heal_and_can_write_again():
    cluster = build(Cluster(["n1", "n2", "n3"]), values=("a",))
    cluster.partition({"n1"}, {"n2", "n3"})
    cluster.append("lost")
    cluster.heal()

    assert cluster.append("b") == 2
    assert cluster.committed_values() == ["a", "b"]
