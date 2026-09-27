"""Visible tests — the learner sees these before submitting."""

import pytest

from solution import (
    BuildCost,
    DockerfileError,
    Instruction,
    cache_miss_index,
    parse_dockerfile,
    rebuild_cost,
    suggest_reorder,
)

TEXT = """FROM python:3.12
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt"""


def test_keywords_are_parsed_in_order():
    parsed = parse_dockerfile(TEXT)

    assert [item.keyword for item in parsed] == ["FROM", "WORKDIR", "COPY", "RUN"]


def test_keywords_are_upper_cased():
    parsed = parse_dockerfile("from python:3.12\nrun echo hi")

    assert [item.keyword for item in parsed] == ["FROM", "RUN"]


def test_arguments_are_captured():
    assert parse_dockerfile("FROM python:3.12")[0].argument == "python:3.12"


def test_blank_lines_and_comments_are_ignored():
    parsed = parse_dockerfile("# a comment\n\nFROM python:3.12\n\n# another")

    assert len(parsed) == 1


def test_a_continuation_is_joined():
    parsed = parse_dockerfile("RUN pip install \\\n    -r requirements.txt")

    assert len(parsed) == 1
    assert parsed[0].argument == "pip install -r requirements.txt"


def test_a_bad_line_is_rejected():
    with pytest.raises(DockerfileError):
        parse_dockerfile("JUSTAKEYWORD")


def test_a_source_change_misses_at_the_copy():
    assert cache_miss_index(parse_dockerfile(TEXT), {"src/app.py"}) == 2


def test_nothing_changing_is_a_full_cache_hit():
    assert cache_miss_index(parse_dockerfile(TEXT), set()) is None


def test_a_context_change_rebuilds_everything():
    assert cache_miss_index(parse_dockerfile(TEXT), {"__everything__"}) == 0


def test_rebuild_cost_counts_the_surviving_cache():
    cost = rebuild_cost(parse_dockerfile(TEXT), {"src/app.py"})

    assert cost == BuildCost(misses=2, rebuilds=2, skipped=2, ratio=0.5)


def test_an_empty_dockerfile_costs_nothing():
    cost = rebuild_cost([], set())

    assert cost == BuildCost(misses=0, rebuilds=0, skipped=0, ratio=1.0)


def test_reorder_moves_the_copy_after_the_run():
    reordered = suggest_reorder(parse_dockerfile(TEXT))

    assert [item.keyword for item in reordered] == ["FROM", "WORKDIR", "RUN", "COPY"]


def test_reorder_leaves_a_dockerfile_without_a_context_copy_alone():
    parsed = parse_dockerfile("FROM python:3.12\nRUN echo hi")

    assert suggest_reorder(parsed) == parsed
