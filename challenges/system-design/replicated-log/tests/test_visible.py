"""Visible tests — the basic contract for each module."""

import pytest

from cluster import Cluster, Quorum, majority
from log import Entry, LogError, ReplicatedLog
from node import Node


# --- log -----------------------------------------------------------------
def test_an_empty_log_has_no_last_index():
    assert ReplicatedLog().last_index == 0


def test_an_empty_log_has_no_last_term():
    assert ReplicatedLog().last_term == 0


def test_appending_advances_the_last_index():
    log = ReplicatedLog()
    log.append(Entry(term=1, index=1, value="a"))

    assert log.last_index == 1
    assert log.last_term == 1


def test_entries_are_readable_by_index():
    log = ReplicatedLog()
    log.append(Entry(term=1, index=1, value="a"))

    assert log.get(1).value == "a"


def test_an_absent_index_raises():
    with pytest.raises(IndexError):
        ReplicatedLog().get(1)


def test_appending_a_gap_is_rejected():
    log = ReplicatedLog()

    with pytest.raises(LogError):
        log.append(Entry(term=1, index=5, value="a"))


def test_truncating_removes_the_suffix():
    log = ReplicatedLog()
    for index in (1, 2, 3):
        log.append(Entry(term=1, index=index, value=f"v{index}"))

    log.truncate_from(2)

    assert log.last_index == 1


def test_committing_advances_the_commit_index():
    log = ReplicatedLog()
    log.append(Entry(term=1, index=1, value="a"))
    log.commit(1)

    assert log.commit_index == 1
    assert [entry.value for entry in log.committed] == ["a"]


def test_uncommitted_entries_are_not_in_committed():
    log = ReplicatedLog()
    log.append(Entry(term=1, index=1, value="a"))
    log.append(Entry(term=1, index=2, value="b"))
    log.commit(1)

    assert [entry.value for entry in log.committed] == ["a"]


def test_commit_is_monotonic():
    log = ReplicatedLog()
    log.append(Entry(term=1, index=1, value="a"))
    log.commit(1)

    log.commit(0)

    assert log.commit_index == 1


def test_a_more_current_log_is_up_to_date():
    log = ReplicatedLog()
    log.append(Entry(term=2, index=1, value="a"))

    assert log.is_up_to_date(term=2, index=1) is True


def test_an_older_term_is_not_up_to_date():
    log = ReplicatedLog()
    log.append(Entry(term=2, index=1, value="a"))

    assert log.is_up_to_date(term=1, index=9) is False


# --- node ----------------------------------------------------------------
def test_a_vote_is_granted_to_an_up_to_date_candidate():
    node = Node("n1")

    assert node.grant_vote("n2", term=1, last_index=0, last_term=0) is True
    assert node.voted_for == "n2"


def test_a_second_vote_in_the_same_term_is_refused():
    node = Node("n1")
    node.grant_vote("n2", term=1, last_index=0, last_term=0)

    assert node.grant_vote("n3", term=1, last_index=0, last_term=0) is False


def test_a_stale_candidate_is_refused():
    node = Node("n1")
    node.grant_vote("n2", term=3, last_index=0, last_term=0)

    assert node.grant_vote("n3", term=2, last_index=0, last_term=0) is False


def test_an_append_with_a_matching_prefix_is_accepted():
    node = Node("n1")

    assert node.handle_append(1, 0, 0, [Entry(1, 1, "a")]) is True
    assert node.log.last_index == 1


def test_an_append_from_a_stale_leader_is_refused():
    node = Node("n1")
    node.handle_append(2, 0, 0, [Entry(2, 1, "a")])

    assert node.handle_append(1, 1, 1, [Entry(1, 2, "b")]) is False
    assert node.log.last_index == 1


def test_restart_keeps_the_log_but_loses_the_vote():
    node = Node("n1")
    node.grant_vote("n2", term=4, last_index=0, last_term=0)
    node.handle_append(4, 0, 0, [Entry(4, 1, "a")])

    node.restart()

    assert node.log.last_index == 1
    assert node.term == 0
    assert node.voted_for is None


# --- cluster -------------------------------------------------------------
def test_majority_of_three_is_two():
    assert majority(3) == 2


def test_a_two_node_group_in_a_three_node_cluster_has_a_majority():
    assert Quorum(["n1", "n2"], total=3).has_majority is True


def test_a_single_node_in_a_three_node_cluster_has_no_majority():
    assert Quorum(["n1"], total=3).has_majority is False


def test_electing_a_leader():
    cluster = Cluster(["n1", "n2", "n3"])

    assert cluster.elect("n1") == "n1"
    assert cluster.leader == "n1"


def test_appending_through_the_leader_commits():
    cluster = Cluster(["n1", "n2", "n3"])
    cluster.elect("n1")

    assert cluster.append("first") == 1
    assert cluster.committed_values() == ["first"]


def test_a_partitioned_minority_cannot_elect():
    cluster = Cluster(["n1", "n2", "n3"])
    cluster.partition({"n1"}, {"n2", "n3"})

    assert cluster.elect("n1") is None


def test_a_partitioned_minority_cannot_commit():
    cluster = Cluster(["n1", "n2", "n3"])
    cluster.elect("n1")
    cluster.partition({"n1"}, {"n2", "n3"})

    assert cluster.append("lost") is None
    assert cluster.committed_values() == []
