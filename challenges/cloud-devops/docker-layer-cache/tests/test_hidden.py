"""Hidden tests — the cache semantics that decide a build's wall time."""

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

GOOD = """FROM python:3.12
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY src/ src/"""


# --- the cascade: one miss invalidates everything after it ----------------
def test_a_miss_cascades_to_every_later_layer():
    """A later layer's cache key includes its parent's, so it cannot hit."""
    miss = cache_miss_index(parse_dockerfile(TEXT), {"src/app.py"})

    assert miss == 2, "the COPY is index 2, so RUN at 3 must also rebuild"


def test_a_run_before_the_copy_stays_cached_when_only_source_changes():
    """This is the whole point of reordering: the install survives."""
    miss = cache_miss_index(parse_dockerfile(GOOD), {"src/app.py"})

    assert miss == 4, f"expected the final COPY to miss, got {miss}"


def test_the_expensive_install_is_cached_when_only_source_changes():
    cost = rebuild_cost(parse_dockerfile(GOOD), {"src/app.py"})

    assert cost.skipped == 4
    assert cost.misses == 1


def test_a_requirements_change_invalidates_the_install():
    miss = cache_miss_index(parse_dockerfile(GOOD), {"requirements.txt"})

    assert miss == 2


def test_everything_changing_misses_at_the_first_layer():
    assert cache_miss_index(parse_dockerfile(GOOD), {"__everything__"}) == 0


# --- path coverage is prefix-based, not string-based ----------------------
def test_a_directory_source_covers_files_beneath_it():
    parsed = parse_dockerfile("FROM x\nCOPY src/ /app/src/")

    assert cache_miss_index(parsed, {"src/app.py"}) == 1


def test_a_prefix_that_is_not_a_path_segment_does_not_cover():
    """'src' must not cover 'srcs/app.py' — that is a different directory."""
    parsed = parse_dockerfile("FROM x\nCOPY src/ /app/src/")

    assert cache_miss_index(parsed, {"srcs/app.py"}) is None


def test_a_source_without_a_trailing_slash_still_covers_its_subtree():
    parsed = parse_dockerfile("FROM x\nCOPY src /app/src")

    assert cache_miss_index(parsed, {"src/deep/app.py"}) == 1


def test_an_unrelated_change_does_not_invalidate_a_scoped_copy():
    parsed = parse_dockerfile("FROM x\nCOPY src/ /app/src/\nCOPY docs/ /app/docs/")

    assert cache_miss_index(parsed, {"docs/readme.md"}) == 2


def test_a_change_outside_every_copy_is_a_full_hit():
    parsed = parse_dockerfile("FROM x\nCOPY src/ /app/src/")

    assert cache_miss_index(parsed, {"unrelated.txt"}) is None


# --- variables ------------------------------------------------------------
def test_an_arg_change_invalidates_the_build():
    parsed = parse_dockerfile("FROM python:3.12\nARG PYTHON_VERSION\nRUN echo hi")

    assert cache_miss_index(parsed, {"ARG:PYTHON_VERSION"}) == 1


def test_an_unrelated_arg_does_not_invalidate():
    parsed = parse_dockerfile("FROM python:3.12\nARG PYTHON_VERSION\nRUN echo hi")

    assert cache_miss_index(parsed, {"ARG:SOMETHING_ELSE"}) is None


def test_an_env_change_invalidates():
    parsed = parse_dockerfile("FROM x\nENV MODE=prod\nRUN echo hi")

    assert cache_miss_index(parsed, {"ENV:MODE"}) == 1


# --- parsing --------------------------------------------------------------
def test_whitespace_in_a_continuation_is_collapsed():
    parsed = parse_dockerfile("RUN apt-get update \\\n   &&   apt-get install -y curl")

    assert parsed[0].argument == "apt-get update && apt-get install -y curl"


def test_a_comment_inside_a_continuation_does_not_split_it():
    parsed = parse_dockerfile("RUN echo a \\\n    && echo b")

    assert len(parsed) == 1
    assert parsed[0].argument == "echo a && echo b"


def test_repeated_parses_are_identical():
    first = parse_dockerfile(TEXT)
    second = parse_dockerfile(TEXT)

    assert first == second


def test_an_empty_dockerfile_parses_to_nothing():
    assert parse_dockerfile("") == []
    assert parse_dockerfile("\n\n# only a comment\n") == []


def test_a_keyword_with_no_argument_is_rejected():
    with pytest.raises(DockerfileError):
        parse_dockerfile("FROM")


def test_a_json_form_copy_is_understood():
    parsed = parse_dockerfile('FROM x\nCOPY ["src", "/app/src"]')

    assert cache_miss_index(parsed, {"src/app.py"}) == 1


# --- cost arithmetic ------------------------------------------------------
def test_the_ratio_is_skipped_over_total():
    cost = rebuild_cost(parse_dockerfile("FROM x\nRUN a\nRUN b\nRUN c"), {"unrelated"})

    assert cost == BuildCost(misses=0, rebuilds=0, skipped=4, ratio=1.0)


def test_a_full_miss_has_a_zero_ratio():
    cost = rebuild_cost(parse_dockerfile("FROM x\nRUN a"), {"__everything__"})

    assert cost.ratio == 0.0


def test_misses_and_rebuilds_agree():
    cost = rebuild_cost(parse_dockerfile(TEXT), {"src/app.py"})

    assert cost.misses == cost.rebuilds


def test_skipped_plus_misses_is_the_total():
    parsed = parse_dockerfile(GOOD)
    cost = rebuild_cost(parsed, {"src/app.py"})

    assert cost.skipped + cost.misses == len(parsed)


# --- reordering -----------------------------------------------------------
def test_reordering_moves_the_copy_after_the_last_run():
    reordered = suggest_reorder(parse_dockerfile(TEXT))

    assert [item.keyword for item in reordered] == ["FROM", "WORKDIR", "RUN", "COPY"]


def test_reordering_preserves_the_relative_order_of_the_rest():
    parsed = parse_dockerfile("FROM x\nCOPY . .\nRUN a\nRUN b\nWORKDIR /w")
    reordered = suggest_reorder(parsed)

    assert [item.keyword for item in reordered] == ["FROM", "RUN", "RUN", "COPY", "WORKDIR"]
    assert [item.argument for item in reordered] == ["x", "a", "b", ". .", "/w"]


def test_reordering_moves_multiple_copies_together_preserving_their_order():
    parsed = parse_dockerfile("FROM x\nCOPY . .\nRUN a\nADD . /app")
    reordered = suggest_reorder(parsed)

    assert [item.keyword for item in reordered] == ["FROM", "RUN", "COPY", "ADD"]


def test_reordering_the_already_good_file_changes_nothing():
    parsed = parse_dockerfile(GOOD)

    assert suggest_reorder(parsed) == parsed


def test_reordering_does_not_mutate_the_input():
    parsed = parse_dockerfile(TEXT)
    snapshot = list(parsed)

    suggest_reorder(parsed)

    assert parsed == snapshot


def test_reordering_without_a_run_is_a_no_op():
    parsed = parse_dockerfile("FROM x\nCOPY . .")

    assert suggest_reorder(parsed) == parsed


def test_reordering_improves_the_surviving_cache():
    """The suggestion must actually pay off, measured the same way as the cost."""
    before = rebuild_cost(parse_dockerfile(TEXT), {"src/app.py"})
    after = rebuild_cost(suggest_reorder(parse_dockerfile(TEXT)), {"src/app.py"})

    assert after.skipped > before.skipped


def test_reordering_keeps_the_run_cached_on_a_source_change():
    reordered = suggest_reorder(parse_dockerfile(TEXT))
    miss = cache_miss_index(reordered, {"src/app.py"})

    assert miss == 3, "the RUN at index 2 must not rebuild"
    assert reordered[miss].keyword == "COPY"


def test_a_scoped_copy_is_not_moved():
    """Only whole-context copies are the anti-pattern."""
    parsed = parse_dockerfile("FROM x\nRUN a\nCOPY src/ src/")
    reordered = suggest_reorder(parsed)
    run_index = next(i for i, item in enumerate(reordered) if item.keyword == "RUN")
    copy_index = next(i for i, item in enumerate(reordered) if item.keyword == "COPY")

    assert run_index < copy_index
    assert len(reordered) == len(parsed)


def test_an_instruction_object_is_returned_unchanged_by_reorder():
    parsed = [Instruction("FROM", "x"), Instruction("RUN", "a"), Instruction("COPY", ". .")]
    reordered = suggest_reorder(parsed)

    assert reordered[2] == Instruction("COPY", ". .")
