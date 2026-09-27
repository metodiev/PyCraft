"""Visible tests — the learner sees these before submitting."""

import pytest

from solution import (
    CycleError,
    critical_path,
    single_points_of_failure,
    transitive_dependents,
)

GRAPH = {
    "web": ["api"],
    "api": ["db"],
    "db": [],
    "worker": ["db"],
}


def test_direct_dependents_are_reported():
    assert transitive_dependents(GRAPH, "api") == ["web"]


def test_dependents_are_transitive():
    assert transitive_dependents(GRAPH, "db") == ["api", "web", "worker"]


def test_a_leaf_has_no_dependents():
    assert transitive_dependents({"web": [], "api": []}, "api") == []


def test_the_failed_component_is_excluded():
    assert "api" not in transitive_dependents(GRAPH, "api")


def test_results_are_sorted():
    graph = {"a": ["target"], "b": ["target"], "c": ["target"], "target": []}

    assert transitive_dependents(graph, "target") == ["a", "b", "c"]


def test_the_most_dependent_component_ranks_first():
    ranked = single_points_of_failure(GRAPH)

    assert ranked[0] == ("db", 3)


def test_every_component_appears_in_the_ranking():
    ranked = single_points_of_failure(GRAPH)

    assert len(ranked) == 4
    assert {name for name, _ in ranked} == set(GRAPH)


def test_ties_are_broken_by_name():
    graph = {"a": [], "b": []}

    assert single_points_of_failure(graph) == [("a", 0), ("b", 0)]


def test_critical_path_ends_at_the_target():
    assert critical_path(GRAPH, "web") == ["db", "api", "web"]


def test_critical_path_of_a_leaf_is_itself():
    assert critical_path(GRAPH, "db") == ["db"]


def test_a_cycle_is_reported_not_hung():
    graph = {"a": ["b"], "b": ["a"]}

    with pytest.raises(CycleError):
        critical_path(graph, "a")


def test_error_message_names_the_components():
    graph = {"a": ["b"], "b": ["a"]}

    with pytest.raises(CycleError) as caught:
        critical_path(graph, "a")

    assert "a" in str(caught.value)
    assert "b" in str(caught.value)
