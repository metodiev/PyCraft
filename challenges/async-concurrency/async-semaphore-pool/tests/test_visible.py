"""Visible tests — the learner sees these before submitting."""

import asyncio

import pytest

from solution import run_pool


async def double(n):
    await asyncio.sleep(0)
    return n * 2


async def boom():
    raise ValueError("no")


@pytest.mark.asyncio
async def test_returns_results_in_order():
    jobs = [lambda index=index: double(index) for index in range(5)]
    assert await run_pool(jobs, 2) == [(index, index * 2) for index in range(5)]


@pytest.mark.asyncio
async def test_empty_job_list():
    assert await run_pool([], 3) == []


@pytest.mark.asyncio
async def test_errors_are_returned_not_raised():
    results = await run_pool([lambda: double(3), boom], 4)
    assert results[0] == (0, 6)
    index, error = results[1]
    assert index == 1
    assert isinstance(error, ValueError)


@pytest.mark.asyncio
async def test_rejects_invalid_worker_counts():
    for bad in (0, -1):
        with pytest.raises(ValueError):
            await run_pool([], bad)
