"""Visible tests — the learner sees these before submitting."""

import pytest

from solution import dependency_graph, diff_resources, plan, resource_type

DESIRED = {
    "aws_ami.base": {"name": "pycraft-base"},
    "aws_instance.web": {
        "ami": "${aws_ami.base.id}",
        "instance_type": "t3.micro",
    },
}
ACTUAL = {"aws_ami.base": {"name": "pycraft-base", "id": "ami-1"}}


def test_resource_type_splits_the_address():
    assert resource_type("aws_vpc.main") == "aws_vpc"
    assert resource_type("module.network") == "module"


def test_a_malformed_address_is_rejected():
    with pytest.raises(ValueError):
        resource_type("aws_vpc")


def test_dependencies_are_resolved_from_interpolations():
    assert dependency_graph(DESIRED) == {
        "aws_ami.base": [],
        "aws_instance.web": ["aws_ami.base"],
    }


def test_only_declared_attributes_are_compared():
    changes = diff_resources(DESIRED, ACTUAL)
    by_address = {change["address"]: change for change in changes}

    # "id" is reported by the provider and not declared, so it is not a change.
    assert by_address["aws_ami.base"]["action"] == "no-op"
    assert by_address["aws_ami.base"]["changed"] == []
    assert by_address["aws_instance.web"]["action"] == "create"


def test_a_missing_resource_is_created():
    change = diff_resources({"aws_s3_bucket.logs": {"bucket": "logs"}}, {})[0]

    assert change["action"] == "create"
    assert change["changed"] == ["bucket"]


def test_an_undeclared_resource_is_deleted():
    change = diff_resources({}, {"aws_s3_bucket.old": {"bucket": "old"}})[0]

    assert change["action"] == "delete"
    assert change["changed"] == []


def test_plan_reports_counts():
    result = plan(DESIRED, ACTUAL)

    assert result["summary"] == {
        "create": 1,
        "update": 0,
        "replace": 0,
        "delete": 0,
        "no-op": 1,
        "total": 2,
    }


def test_plan_orders_creates_by_dependency():
    addresses = [change["address"] for change in plan(DESIRED, ACTUAL)["changes"]]

    assert addresses.index("aws_ami.base") < addresses.index("aws_instance.web")


def test_planning_does_not_mutate_its_arguments():
    desired = {address: dict(body) for address, body in DESIRED.items()}
    actual = {address: dict(body) for address, body in ACTUAL.items()}
    desired_snapshot = {address: dict(body) for address, body in desired.items()}
    actual_snapshot = {address: dict(body) for address, body in actual.items()}

    plan(desired, actual)

    assert desired == desired_snapshot
    assert actual == actual_snapshot
