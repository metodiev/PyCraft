"""Hidden tests — determinism, failure propagation and cache accounting."""

import pytest

from solution import (
    PipelineCycleError,
    PipelineError,
    execution_order,
    parallel_waves,
    schedule,
)

FAN = [
    {"name": "test", "needs": [], "cache": None},
    {"name": "build", "needs": [], "cache": "deps-v2"},
    {"name": "deploy", "needs": ["build", "test"], "cache": None},
]


# --- deterministic ordering ----------------------------------------------
def test_ready_jobs_are_emitted_in_name_order():
    assert execution_order(FAN) == ["build", "test", "deploy"]


def test_the_order_does_not_depend_on_declaration_order():
    reversed_pipeline = list(reversed(FAN))

    assert execution_order(reversed_pipeline) == execution_order(FAN)
    assert parallel_waves(reversed_pipeline) == parallel_waves(FAN)


def test_an_independent_job_declared_last_is_not_delayed():
    jobs = [
        {"name": "zulu", "needs": ["parent"]},
        {"name": "parent", "needs": []},
        {"name": "alpha", "needs": []},
    ]

    assert execution_order(jobs) == ["alpha", "parent", "zulu"]


def test_every_dependency_precedes_its_dependent():
    order = execution_order(FAN)
    position = {name: index for index, name in enumerate(order)}

    for job in FAN:
        for need in job["needs"]:
            assert position[need] < position[job["name"]]


def test_a_long_chain_stays_in_order():
    jobs = [{"name": f"j{index}", "needs": [f"j{index - 1}"]} for index in range(1, 8)]
    jobs.append({"name": "j0", "needs": []})

    assert execution_order(jobs) == [f"j{index}" for index in range(8)]


# --- waves ---------------------------------------------------------------
def test_a_job_sits_after_its_latest_dependency():
    """``c`` must wait for ``b``, even though its first dependency is ready."""
    jobs = [
        {"name": "a", "needs": []},
        {"name": "b", "needs": ["a"]},
        {"name": "c", "needs": ["a", "b"]},
    ]

    assert parallel_waves(jobs) == [["a"], ["b"], ["c"]]


def test_no_wave_places_a_job_with_its_own_dependency():
    waves = parallel_waves(FAN)
    position = {name: index for index, wave in enumerate(waves) for name in wave}

    for job in FAN:
        for need in job["needs"]:
            assert position[need] < position[job["name"]]


def test_a_diamond_fans_out_and_back_in():
    jobs = [
        {"name": "start", "needs": []},
        {"name": "left", "needs": ["start"]},
        {"name": "right", "needs": ["start"]},
        {"name": "end", "needs": ["left", "right"]},
    ]

    assert parallel_waves(jobs) == [["start"], ["left", "right"], ["end"]]


def test_waves_cover_every_job_exactly_once():
    waves = parallel_waves(FAN)
    flattened = [name for wave in waves for name in wave]

    assert sorted(flattened) == ["build", "deploy", "test"]
    assert len(flattened) == len(set(flattened))


# --- failure propagation -------------------------------------------------
def test_a_failed_dependency_skips_its_dependent():
    jobs = [{"name": "build", "needs": []}, {"name": "test", "needs": ["build"]}]

    result = schedule(jobs, failures=["build"])

    assert result["statuses"] == {"build": "failed", "test": "skipped"}


def test_a_skip_itself_skips_everything_further_downstream():
    jobs = [
        {"name": "build", "needs": []},
        {"name": "test", "needs": ["build"]},
        {"name": "deploy", "needs": ["test"]},
        {"name": "unrelated", "needs": []},
    ]

    result = schedule(jobs, failures=["build"])

    assert result["statuses"] == {
        "build": "failed",
        "test": "skipped",
        "deploy": "skipped",
        "unrelated": "success",
    }


def test_allow_failure_keeps_dependents_running():
    jobs = [
        {"name": "scan", "needs": [], "allow_failure": True},
        {"name": "release", "needs": ["scan"]},
    ]

    result = schedule(jobs, failures=["scan"])

    assert result["statuses"] == {"scan": "failed", "release": "success"}
    assert result["summary"] == {
        "success": 1,
        "failed": 1,
        "skipped": 0,
        "cache_hits": 0,
    }


def test_allow_failure_does_not_skip_the_rest_of_the_pipeline():
    jobs = [
        {"name": "scan", "needs": [], "allow_failure": True},
        {"name": "build", "needs": ["scan"]},
        {"name": "test", "needs": ["build"]},
    ]

    result = schedule(jobs, failures=["scan"])

    assert result["statuses"] == {
        "scan": "failed",
        "build": "success",
        "test": "success",
    }


def test_a_dependent_of_an_allowed_failure_is_still_skipped_if_it_fails():
    jobs = [
        {"name": "scan", "needs": [], "allow_failure": True},
        {"name": "release", "needs": ["scan"]},
        {"name": "announce", "needs": ["release"]},
    ]

    result = schedule(jobs, failures=["scan", "release"])

    assert result["statuses"] == {
        "scan": "failed",
        "release": "failed",
        "announce": "skipped",
    }


def test_a_strict_failure_blocks_only_its_own_subtree():
    """A job that a failed one merely starts with is not a blocker."""
    jobs = [
        {"name": "build", "needs": []},
        {"name": "docs", "needs": []},
        {"name": "package", "needs": ["build"]},
        {"name": "publish", "needs": ["package"]},
    ]

    result = schedule(jobs, failures=["build"])

    assert result["statuses"] == {
        "build": "failed",
        "docs": "success",
        "package": "skipped",
        "publish": "skipped",
    }


# --- cache accounting ----------------------------------------------------
def test_a_failed_job_never_publishes_its_cache():
    jobs = [
        {"name": "build", "needs": [], "cache": "shared"},
        {"name": "package", "needs": [], "cache": "shared"},
        {"name": "test", "needs": ["build"], "cache": "shared"},
    ]

    result = schedule(jobs, failures=["build"])

    assert result["cache_misses"] == ["package"]
    assert result["cache_hits"] == []
    assert result["statuses"]["test"] == "skipped"


def test_a_skipped_job_neither_hits_nor_warms_the_cache():
    jobs = [
        {"name": "build", "needs": [], "cache": None},
        {"name": "package", "needs": ["build"], "cache": "artifacts"},
        {"name": "publish", "needs": ["package"], "cache": "artifacts"},
    ]

    result = schedule(jobs, failures=["build"])

    assert result["cache_hits"] == []
    assert result["cache_misses"] == []


def test_cache_matching_is_by_key_not_by_job_name():
    jobs = [
        {"name": "a", "needs": [], "cache": "same"},
        {"name": "b", "needs": [], "cache": "different"},
        {"name": "c", "needs": [], "cache": "same"},
    ]

    result = schedule(jobs)

    # Order is a, b, c; "b" has its own key, so only "c" reuses "a"'s.
    assert result["cache_misses"] == ["a", "b"]
    assert result["cache_hits"] == ["c"]


def test_jobs_without_a_cache_key_are_excluded_entirely():
    jobs = [{"name": "a", "needs": []}, {"name": "b", "needs": ["a"], "cache": None}]

    result = schedule(jobs)

    assert result["cache_hits"] == []
    assert result["cache_misses"] == []
    assert result["summary"]["cache_hits"] == 0


def test_a_cache_hit_needs_an_earlier_successful_warm():
    jobs = [
        {"name": "later", "needs": ["earlier"], "cache": "k"},
        {"name": "earlier", "needs": [], "cache": None},
    ]

    result = schedule(jobs)

    # The only warm of "k" happens after the miss, so nothing ever hits.
    assert result["cache_hits"] == []
    assert result["cache_misses"] == ["later"]


def test_cache_hits_are_reported_in_execution_order():
    jobs = [
        {"name": "one", "needs": [], "cache": "k"},
        {"name": "two", "needs": ["one"], "cache": "k"},
        {"name": "three", "needs": ["two"], "cache": "k"},
        {"name": "four", "needs": ["three"], "cache": "k"},
    ]

    result = schedule(jobs)

    assert result["cache_misses"] == ["one"]
    assert result["cache_hits"] == ["two", "three", "four"]


def test_the_summary_counts_every_status():
    jobs = [
        {"name": "build", "needs": [], "cache": "k"},
        {"name": "test", "needs": ["build"], "cache": "k"},
        {"name": "scan", "needs": [], "cache": None, "allow_failure": True},
        {"name": "docs", "needs": [], "cache": None},
    ]

    result = schedule(jobs, failures=["build", "scan"])

    assert result["statuses"] == {
        "build": "failed",
        "docs": "success",
        "scan": "failed",
        "test": "skipped",
    }
    assert result["summary"] == {
        "success": 1,
        "failed": 2,
        "skipped": 1,
        "cache_hits": 0,
    }


# --- cycles --------------------------------------------------------------
def test_a_cycle_names_every_participant():
    jobs = [
        {"name": "lint", "needs": []},
        {"name": "deploy", "needs": ["build"]},
        {"name": "build", "needs": ["test"]},
        {"name": "test", "needs": ["build"]},
    ]

    with pytest.raises(PipelineCycleError) as excinfo:
        execution_order(jobs)

    assert excinfo.value.jobs == ["build", "test"]
    message = str(excinfo.value)
    assert "build" in message and "test" in message
    # A healthy job that merely depends on the cycle is not a participant.
    assert "deploy" not in message


def test_a_three_job_cycle_is_reported_as_one_group():
    jobs = [
        {"name": "c", "needs": ["b"]},
        {"name": "a", "needs": ["c"]},
        {"name": "b", "needs": ["a"]},
    ]

    with pytest.raises(PipelineCycleError) as excinfo:
        execution_order(jobs)

    assert excinfo.value.jobs == ["a", "b", "c"]


def test_a_self_dependency_is_a_cycle():
    jobs = [{"name": "loop", "needs": ["loop"]}]

    with pytest.raises(PipelineCycleError) as excinfo:
        execution_order(jobs)

    assert excinfo.value.jobs == ["loop"]


def test_parallel_waves_rejects_a_cycle_too():
    jobs = [{"name": "a", "needs": ["b"]}, {"name": "b", "needs": ["a"]}]

    with pytest.raises(PipelineCycleError):
        parallel_waves(jobs)


def test_a_pipeline_with_two_separate_cycles_reports_both():
    jobs = [
        {"name": "a", "needs": ["b"]},
        {"name": "b", "needs": ["a"]},
        {"name": "x", "needs": ["y"]},
        {"name": "y", "needs": ["x"]},
        {"name": "fine", "needs": []},
    ]

    with pytest.raises(PipelineCycleError) as excinfo:
        execution_order(jobs)

    assert excinfo.value.jobs == ["a", "b", "x", "y"]


def test_cycle_error_is_a_pipeline_error():
    jobs = [{"name": "a", "needs": ["a"]}]

    with pytest.raises(PipelineError):
        execution_order(jobs)


# --- input handling ------------------------------------------------------
def test_the_pipeline_is_not_mutated():
    jobs = [dict(job) for job in FAN]
    snapshot = [dict(job) for job in jobs]

    schedule(jobs, failures=["build"])

    assert jobs == snapshot


def test_a_job_needing_a_skipped_job_is_not_reported_as_success():
    jobs = [
        {"name": "build", "needs": []},
        {"name": "test", "needs": ["build"], "allow_failure": True},
        {"name": "deploy", "needs": ["test"]},
    ]

    result = schedule(jobs, failures=["build"])

    # "test" is allowed to fail, but it never ran: it was skipped, and that
    # still blocks "deploy".
    assert result["statuses"] == {
        "build": "failed",
        "test": "skipped",
        "deploy": "skipped",
    }


def test_a_failure_that_names_an_unknown_job_is_rejected():
    with pytest.raises(PipelineError):
        schedule(FAN, failures=["ghost"])


def test_a_failure_that_a_job_could_never_hit_is_rejected():
    """A typo in the failure list must not silently pass the pipeline."""
    with pytest.raises(PipelineError):
        schedule([{"name": "build", "needs": []}], failures=["Build"])
