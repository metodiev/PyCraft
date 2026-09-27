"""Hidden tests — the semantics that make a plan safe to apply."""

import pytest

from solution import dependency_graph, diff_resources, plan, resource_type

NETWORK = {
    "aws_vpc.main": {"cidr_block": "10.0.0.0/16"},
    "aws_subnet.public": {"vpc_id": "${aws_vpc.main.id}"},
    "aws_instance.web": {
        "subnet_id": "${aws_subnet.public.id}",
        "ami": "ami-1",
        "instance_type": "t3.micro",
    },
}


# --- immutable attributes force a replacement -----------------------------
def test_an_immutable_change_is_a_replace_not_an_update():
    change = diff_resources(
        {"aws_instance.web": {"ami": "ami-2", "instance_type": "t3.micro"}},
        {"aws_instance.web": {"ami": "ami-1", "instance_type": "t3.micro"}},
        {"aws_instance": {"ami"}},
    )[0]

    assert change["action"] == "replace"
    assert change["changed"] == ["ami"]


def test_a_mutable_change_on_the_same_type_stays_an_update():
    change = diff_resources(
        {"aws_instance.web": {"ami": "ami-1", "instance_type": "t3.large"}},
        {"aws_instance.web": {"ami": "ami-1", "instance_type": "t3.micro"}},
        {"aws_instance": {"ami"}},
    )[0]

    assert change["action"] == "update"
    assert change["changed"] == ["instance_type"]


def test_replace_wins_when_both_kinds_of_attribute_changed():
    change = diff_resources(
        {"aws_instance.web": {"ami": "ami-2", "instance_type": "t3.large"}},
        {"aws_instance.web": {"ami": "ami-1", "instance_type": "t3.micro"}},
        {"aws_instance": {"ami"}},
    )[0]

    assert change["action"] == "replace"
    assert change["changed"] == ["ami", "instance_type"]


def test_immutability_is_scoped_to_the_resource_type():
    """``ami`` forces a replacement for an instance, not for a data source."""
    change = diff_resources(
        {"aws_ami.latest": {"ami": "ami-2"}},
        {"aws_ami.latest": {"ami": "ami-1"}},
        {"aws_instance": {"ami"}},
    )[0]

    assert change["action"] == "update"


def test_a_missing_immutable_declaration_is_not_a_crash():
    change = diff_resources(
        {"aws_instance.web": {"ami": "ami-2"}},
        {"aws_instance.web": {"ami": "ami-1"}},
    )[0]

    assert change["action"] == "update"


# --- what counts as a change ---------------------------------------------
def test_a_declared_attribute_absent_from_state_is_a_change():
    change = diff_resources(
        {"aws_instance.web": {"ami": "ami-1", "monitoring": True}},
        {"aws_instance.web": {"ami": "ami-1"}},
    )[0]

    assert change["action"] == "update"
    assert change["changed"] == ["monitoring"]


def test_provider_computed_attributes_are_not_changes():
    change = diff_resources(
        {"aws_instance.web": {"ami": "ami-1"}},
        {"aws_instance.web": {"ami": "ami-1", "id": "i-1", "private_ip": "10.0.0.5"}},
    )[0]

    assert change["action"] == "no-op"
    assert change["changed"] == []


def test_nested_values_are_compared_by_value():
    desired = {"aws_instance.web": {"tags": {"Env": "prod"}, "ami": "ami-1"}}
    actual = {"aws_instance.web": {"tags": {"Env": "dev"}, "ami": "ami-1"}}

    change = diff_resources(desired, actual)[0]

    assert change["action"] == "update"
    assert change["changed"] == ["tags"]


def test_a_declared_none_that_matches_the_state_is_unchanged():
    change = diff_resources(
        {"aws_bucket.logs": {"policy": None}},
        {"aws_bucket.logs": {"policy": None, "logging": True}},
    )[0]

    assert change["action"] == "no-op"
    # ``policy`` is declared as None and the state agrees, so it did not change.
    assert change["changed"] == []


# --- declared-absent resources -------------------------------------------
def test_an_explicit_none_deletes_an_existing_resource():
    change = diff_resources({"aws_bucket.old": None}, {"aws_bucket.old": {}})[0]

    assert change["action"] == "delete"


def test_an_explicit_none_that_is_absent_is_not_in_the_plan():
    result = plan({"aws_bucket.old": None}, {})

    assert result["changes"] == []
    assert result["summary"]["total"] == 0


def test_diff_addresses_are_sorted_and_complete():
    changes = diff_resources(
        {"b.two": {}, "a.one": {}},
        {"c.three": {}, "b.two": {}},
    )

    assert [change["address"] for change in changes] == ["a.one", "b.two", "c.three"]


# --- dependency resolution ------------------------------------------------
def test_an_attribute_reference_matches_the_bare_form():
    graph = dependency_graph(
        {
            "aws_vpc.main": {"cidr_block": "10.0.0.0/16"},
            "aws_volume.data": {"vpc_id": "${aws_vpc.main.id}"},
        }
    )

    assert graph["aws_volume.data"] == ["aws_vpc.main"]
    assert graph["aws_vpc.main"] == []


def test_deeply_nested_and_list_references_are_found():
    graph = dependency_graph(
        {
            "aws_security_group.web": {},
            "aws_instance.web": {
                "network_interface": [
                    {"security_groups": ["${aws_security_group.web.id}"]},
                ],
            },
        }
    )

    assert graph["aws_instance.web"] == ["aws_security_group.web"]


def test_references_to_unknown_addresses_are_ignored():
    graph = dependency_graph({"aws_instance.web": {"subnet_id": "${aws_subnet.ghost.id}"}})

    assert graph["aws_instance.web"] == []


def test_a_reference_that_only_shares_a_prefix_does_not_count():
    """``${aws_vpc.mainnet}`` is not a reference to ``aws_vpc.main``."""
    graph = dependency_graph(
        {
            "aws_vpc.main": {},
            "aws_instance.web": {"subnet_id": "${aws_vpc.mainnet_extra.id}"},
        }
    )

    assert graph["aws_instance.web"] == []


def test_multiple_references_are_sorted_and_deduplicated():
    graph = dependency_graph(
        {
            "aws_vpc.main": {},
            "aws_subnet.a": {},
            "aws_instance.web": {
                "subnet_id": "${aws_subnet.a.id}",
                "vpc_id": "${aws_vpc.main.id}",
                "again": "${aws_subnet.a}",
            },
        }
    )

    assert graph["aws_instance.web"] == ["aws_subnet.a", "aws_vpc.main"]


def test_a_self_reference_is_not_a_dependency():
    graph = dependency_graph({"aws_route.self": {"target": "${aws_route.self.id}"}})

    assert graph["aws_route.self"] == []


def test_the_graph_keeps_the_reverse_direction_clean():
    graph = dependency_graph(NETWORK)

    assert graph["aws_vpc.main"] == []
    assert graph["aws_subnet.public"] == ["aws_vpc.main"]
    assert graph["aws_instance.web"] == ["aws_subnet.public"]


# --- ordering -------------------------------------------------------------
def test_creates_follow_the_dependency_chain():
    desired = {
        "aws_instance.web": {
            "subnet_id": "${aws_subnet.public.id}",
            "vpc_id": "${aws_vpc.main.id}",
        },
        "aws_subnet.public": {"vpc_id": "${aws_vpc.main.id}"},
        "aws_vpc.main": {},
    }

    addresses = [change["address"] for change in plan(desired, {})["changes"]]

    assert addresses == ["aws_vpc.main", "aws_subnet.public", "aws_instance.web"]


def test_deletes_run_after_applies():
    desired = {"aws_vpc.fresh": {}}
    actual = {"aws_vpc.old": {}}

    addresses = [change["address"] for change in plan(desired, actual)["changes"]]

    assert addresses == ["aws_vpc.fresh", "aws_vpc.old"]


def test_a_dependent_is_destroyed_before_what_it_references():
    addresses = [
        change["address"] for change in plan({}, NETWORK)["changes"]
    ]

    assert addresses == ["aws_instance.web", "aws_subnet.public", "aws_vpc.main"]


def test_independent_resources_are_ordered_by_address():
    desired = {
        "aws_s3_bucket.z": {},
        "aws_s3_bucket.a": {},
        "aws_s3_bucket.m": {},
    }

    addresses = [change["address"] for change in plan(desired, {})["changes"]]

    assert addresses == ["aws_s3_bucket.a", "aws_s3_bucket.m", "aws_s3_bucket.z"]


def test_input_dictionary_order_does_not_change_the_plan():
    first = dict(NETWORK)
    second = dict(reversed(list(NETWORK.items())))

    assert plan(first, {}) == plan(second, {})


def test_a_cycle_still_emits_every_resource_exactly_once():
    desired = {
        "aws_a.one": {"ref": "${aws_b.two.id}"},
        "aws_b.two": {"ref": "${aws_a.one.id}"},
    }

    result = plan(desired, {})
    addresses = [change["address"] for change in result["changes"]]

    assert sorted(addresses) == ["aws_a.one", "aws_b.two"]
    assert result["summary"]["create"] == 2


def test_the_plan_produces_an_upsert_order_for_mixed_changes():
    desired = {
        "aws_vpc.main": {"cidr_block": "10.1.0.0/16"},
        "aws_subnet.public": {"vpc_id": "${aws_vpc.main.id}", "cidr_block": "10.1.1.0/24"},
        "aws_instance.web": {"subnet_id": "${aws_subnet.public.id}", "ami": "ami-2"},
    }
    actual = {
        "aws_vpc.main": {"cidr_block": "10.0.0.0/16"},
        "aws_instance.web": {
            "subnet_id": "${aws_subnet.public.id}",
            "ami": "ami-1",
        },
        "aws_legacy.old": {},
    }

    result = plan(desired, actual, {"aws_instance": {"ami"}})
    ordered = [(change["address"], change["action"]) for change in result["changes"]]

    assert ordered == [
        ("aws_vpc.main", "update"),
        ("aws_subnet.public", "create"),
        ("aws_instance.web", "replace"),
        ("aws_legacy.old", "delete"),
    ]
    assert result["summary"] == {
        "create": 1,
        "update": 1,
        "replace": 1,
        "delete": 1,
        "no-op": 0,
        "total": 4,
    }


def test_planning_does_not_mutate_its_arguments():
    desired = {address: dict(body) for address, body in NETWORK.items()}
    actual = {"aws_vpc.main": {"cidr_block": "10.0.0.0/16"}}
    desired_snapshot = {address: dict(body) for address, body in desired.items()}
    actual_snapshot = {address: dict(body) for address, body in actual.items()}

    plan(desired, actual, {"aws_instance": {"ami"}})

    assert desired == desired_snapshot
    assert actual == actual_snapshot


def test_a_non_mapping_body_is_rejected():
    with pytest.raises(ValueError):
        dependency_graph({"aws_vpc.main": ["not", "a", "mapping"]})
