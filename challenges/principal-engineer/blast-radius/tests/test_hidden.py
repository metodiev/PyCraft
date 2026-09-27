"""Hidden tests — the graph details that decide real incidents."""

import pytest

from solution import (
    CycleError,
    critical_path,
    single_points_of_failure,
    transitive_dependents,
)

GRAPH = {
    "web": ["api", "cdn"],
    "api": ["db", "cache"],
    "db": ["disk"],
    "cache": ["redis"],
    "worker": ["db"],
    "cdn": [],
    "disk": [],
    "redis": [],
    "metrics": ["prometheus"],
    "prometheus": [],
    "logs": [],
}


# --- transitive dependents ------------------------------------------------
def test_a_component_with_no_dependents_returns_empty():
    # Nothing depends on `logs`, so its failure takes nothing else down.
    assert transitive_dependents(GRAPH, "logs") == []


def test_nested_dependencies_propagate_the_whole_way_up():
    """db -> api -> web; the web must be reported for a db failure."""
    assert transitive_dependents(GRAPH, "db") == ["api", "web", "worker"]


def test_a_deep_leaf_reaches_everything_above_it():
    assert transitive_dependents(GRAPH, "disk") == ["api", "db", "web", "worker"]


def test_a_sibling_branch_is_not_reported():
    """cdn does not depend on api, so an api failure must not include it."""
    dependents = transitive_dependents(GRAPH, "api")

    assert "cdn" not in dependents
    assert "cache" not in dependents


def test_a_diamond_is_not_double_counted():
    """Two routes to the same dependent must yield it once."""
    graph = {"web": ["a", "b"], "a": ["shared"], "b": ["shared"], "shared": []}

    assert transitive_dependents(graph, "shared") == ["a", "b", "web"]


def test_a_component_absent_from_the_graph_can_still_be_analysed():
    """An edge naming an unknown node makes it a leaf, not an error."""
    graph = {"web": ["ghost"]}

    assert transitive_dependents(graph, "ghost") == ["web"]


def test_an_empty_graph_has_no_dependents():
    assert transitive_dependents({}, "anything") == []


# --- single points of failure ---------------------------------------------
def test_the_ranking_is_descending_by_radius():
    ranked = single_points_of_failure(GRAPH)
    radii = [count for _, count in ranked]

    assert radii == sorted(radii, reverse=True)


def test_a_deep_dependency_outranks_a_shallow_one():
    ranked = dict(single_points_of_failure(GRAPH))

    # disk takes out db, api, web, worker; cache only takes out api and web.
    assert ranked["disk"] > ranked["cache"]


def test_components_with_no_dependents_are_included_with_zero():
    ranked = dict(single_points_of_failure(GRAPH))

    assert ranked["logs"] == 0
    assert ranked["prometheus"] == 1  # metrics depends on it


def test_the_ranking_counts_each_dependent_once():
    ranked = dict(single_points_of_failure(GRAPH))

    assert ranked["db"] == 3  # api, web, worker


def test_a_star_graph_ranks_the_hub_first():
    graph = {f"leaf{index}": ["hub"] for index in range(5)} | {"hub": []}
    ranked = single_points_of_failure(graph)

    assert ranked[0] == ("hub", 5)


def test_the_ranking_is_deterministic():
    first = single_points_of_failure(GRAPH)
    second = single_points_of_failure(GRAPH)

    assert first == second


def test_an_empty_graph_ranks_nothing():
    assert single_points_of_failure({}) == []


def test_ties_are_ordered_by_name_not_iteration_order():
    graph = {"z": [], "a": [], "m": []}

    assert single_points_of_failure(graph) == [("a", 0), ("m", 0), ("z", 0)]


# --- critical path --------------------------------------------------------
def test_the_longest_chain_wins():
    assert critical_path(GRAPH, "web") == ["disk", "db", "api", "web"]


def test_the_shorter_branch_is_not_chosen():
    path = critical_path(GRAPH, "web")

    assert "cache" not in path
    assert "cdn" not in path


def test_equal_length_chains_break_lexicographically_from_the_deep_end():
    """Both chains are length 3. Comparing from the deep end prefers 'aaa';
    comparing from the surface end would prefer 'bbb' instead."""
    graph = {"top": ["x", "y"], "x": ["bbb"], "y": ["aaa"], "bbb": [], "aaa": []}

    assert critical_path(graph, "top") == ["aaa", "y", "top"]


def test_the_tie_break_is_not_the_surface_end():
    """Guard the direction explicitly: the other reading gives ['bbb', 'x', 'top']."""
    graph = {"top": ["x", "y"], "x": ["bbb"], "y": ["aaa"], "bbb": [], "aaa": []}

    assert critical_path(graph, "top") != ["bbb", "x", "top"]


def test_an_unknown_target_is_a_single_node_path():
    assert critical_path({"web": ["api"]}, "ghost") == ["ghost"]


def test_a_component_is_never_repeated_in_the_path():
    path = critical_path(GRAPH, "web")

    assert len(path) == len(set(path))


def test_the_path_is_a_real_chain_of_edges():
    """Each consecutive pair must be an actual dependency."""
    path = critical_path(GRAPH, "web")

    for dependent, dependency in zip(path[1:], path[:-1]):
        assert dependency in GRAPH[dependent], f"{dependent} does not depend on {dependency}"


def test_the_path_starts_at_the_target():
    assert critical_path(GRAPH, "worker")[-1] == "worker"


# --- cycles ---------------------------------------------------------------
def test_self_dependency_is_a_cycle():
    with pytest.raises(CycleError):
        critical_path({"a": ["a"]}, "a")


def test_a_longer_cycle_is_detected():
    graph = {"a": ["b"], "b": ["c"], "c": ["a"]}

    with pytest.raises(CycleError):
        critical_path(graph, "a")


def test_dependents_of_a_cyclic_graph_raise_rather_than_hang():
    """Terminating with an error beats a request that never returns."""
    graph = {"a": ["b"], "b": ["a"]}

    with pytest.raises(CycleError):
        transitive_dependents(graph, "a")


def test_the_cycle_error_names_every_participant():
    graph = {"a": ["b"], "b": ["c"], "c": ["a"]}

    with pytest.raises(CycleError) as caught:
        transitive_dependents(graph, "a")
    message = str(caught.value)

    for name in ("a", "b", "c"):
        assert name in message


def test_a_diamond_is_not_mistaken_for_a_cycle():
    """Revisiting a node by a second route is not a cycle."""
    graph = {"web": ["a", "b"], "a": ["shared"], "b": ["shared"], "shared": []}

    assert transitive_dependents(graph, "shared") == ["a", "b", "web"]


# --- input handling -------------------------------------------------------
def test_the_input_graph_is_not_mutated():
    graph = {"web": ["api"], "api": []}
    snapshot = {key: list(value) for key, value in graph.items()}

    transitive_dependents(graph, "api")
    single_points_of_failure(graph)
    critical_path(graph, "web")

    assert graph == snapshot


def test_lists_are_accepted_as_well_as_other_sequences():
    graph = {"web": ("api",), "api": []}

    assert transitive_dependents(graph, "api") == ["web"]


def test_duplicate_edges_do_not_inflate_the_radius():
    graph = {"web": ["api", "api"], "api": []}

    assert transitive_dependents(graph, "api") == ["web"]
    assert dict(single_points_of_failure(graph))["api"] == 1
