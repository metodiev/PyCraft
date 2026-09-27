"""Schedule a CI pipeline expressed as a job DAG.

The tests import ``PipelineCycleError``, ``PipelineError``, ``execution_order``,
``parallel_waves`` and ``schedule`` from here.
"""

from __future__ import annotations


class PipelineError(ValueError):
    """Raised when a pipeline definition is not a usable DAG."""


class PipelineCycleError(PipelineError):
    """Raised when jobs depend on each other in a cycle.

    ``jobs`` holds the names of the jobs that participate in a cycle, sorted.
    """

    def __init__(self, jobs):
        self.jobs = sorted(jobs)
        # TODO: build a message that names every participating job.
        raise NotImplementedError("Complete the PipelineCycleError message")


def execution_order(jobs):
    """Return a dependency-respecting order of job names.

    Ties are broken by ascending job name, so the same pipeline always produces
    the same order whatever order the jobs were declared in.

    >>> execution_order([{"name": "test", "needs": ["build"]}, {"name": "build"}])
    ['build', 'test']
    """
    # TODO: Kahn's algorithm, taking the alphabetically first ready jobs first.
    raise NotImplementedError("Complete the execution_order function")


def parallel_waves(jobs):
    """Group the jobs into waves that can each run in parallel.

    >>> parallel_waves([{"name": "a"}, {"name": "b", "needs": ["a"]}])
    [['a'], ['b']]
    """
    # TODO: a job sits one wave after its last dependency; sort inside a wave.
    raise NotImplementedError("Complete the parallel_waves function")


def schedule(jobs, failures=()):
    """Run the pipeline and report what happened to every job.

    ``failures`` names the jobs whose commands fail. Returns a dict with
    ``statuses``, ``order``, ``waves``, ``cache_hits``, ``cache_misses`` and a
    ``summary``.
    """
    # TODO: walk the order, propagate skips, and count cache reuse.
    raise NotImplementedError("Complete the schedule function")
