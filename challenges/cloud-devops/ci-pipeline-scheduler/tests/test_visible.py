"""Visible tests — the learner sees these before submitting."""

import pytest

from solution import (
    PipelineCycleError,
    PipelineError,
    execution_order,
    parallel_waves,
    schedule,
)

PIPELINE = [
    {"name": "build", "needs": [], "cache": "toolchain-v1"},
    {"name": "lint", "needs": [], "cache": None},
    {"name": "flaky", "needs": [], "cache": None, "allow_failure": True},
    {"name": "package", "needs": ["build"], "cache": "toolchain-v1"},
    {"name": "test", "needs": ["build"], "cache": None},
]


def test_execution_order_respects_dependencies():
    order = execution_order(PIPELINE)

    assert sorted(order) == ["build", "flaky", "lint", "package", "test"]
    position = {name: index for index, name in enumerate(order)}
    assert position["build"] < position["package"]
    assert position["build"] < position["test"]


def test_every_dependency_precedes_its_dependent():
    position = {name: index for index, name in enumerate(execution_order(PIPELINE))}

    for job in PIPELINE:
        for need in job["needs"]:
            assert position[need] < position[job["name"]]


def test_waves_group_work_that_can_run_in_parallel():
    assert parallel_waves(PIPELINE) == [
        ["build", "flaky", "lint"],
        ["package", "test"],
    ]


def test_a_successful_run_reports_every_job():
    result = schedule(PIPELINE)

    assert result["statuses"] == {
        "build": "success",
        "flaky": "success",
        "lint": "success",
        "package": "success",
        "test": "success",
    }
    assert result["order"] == execution_order(PIPELINE)
    assert result["summary"]["success"] == 5
    assert result["summary"]["failed"] == 0


def test_a_failure_skips_everything_downstream():
    result = schedule(PIPELINE, failures=["build"])

    assert result["statuses"]["build"] == "failed"
    assert result["statuses"]["lint"] == "success"
    assert result["statuses"]["package"] == "skipped"
    assert result["statuses"]["test"] == "skipped"
    assert result["summary"]["skipped"] == 2
    assert result["summary"]["failed"] == 1


def test_cache_keys_are_reused_across_jobs():
    result = schedule(PIPELINE)

    assert result["cache_misses"] == ["build"]
    assert result["cache_hits"] == ["package"]
    assert result["summary"]["cache_hits"] == 1


def test_an_empty_pipeline_is_valid():
    assert execution_order([]) == []
    assert parallel_waves([]) == []

    result = schedule([])

    assert result["statuses"] == {}
    assert result["summary"]["cache_hits"] == 0


def test_an_unknown_dependency_is_rejected():
    with pytest.raises(PipelineError):
        execution_order([{"name": "test", "needs": ["missing"]}])


def test_a_duplicate_job_name_is_rejected():
    with pytest.raises(PipelineError):
        execution_order([{"name": "build"}, {"name": "build"}])


def test_a_cycle_is_reported():
    jobs = [{"name": "a", "needs": ["b"]}, {"name": "b", "needs": ["a"]}]

    with pytest.raises(PipelineCycleError):
        execution_order(jobs)
