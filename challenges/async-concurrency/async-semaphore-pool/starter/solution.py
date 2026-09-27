async def run_pool(jobs, workers):
    """Run ``jobs`` with at most ``workers`` coroutines in flight.

    Returns ``[(index, result_or_exception), ...]`` in job order. Validation and
    laziness are part of the contract: ``jobs`` is consumed lazily and a job that
    raises contributes its exception object to the result list.

    >>> import asyncio
    >>> async def double(n):
    ...     await asyncio.sleep(0)
    ...     return n * 2
    >>> asyncio.run(run_pool([lambda: double(1)], 1))
    [(0, 2)]
    """
    # TODO: spawn bounded workers over a queue fed by a producer, collecting one
    # (index, result_or_exception) per job.
    raise NotImplementedError("Complete the run_pool function")
