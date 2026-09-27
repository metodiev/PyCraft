"""Challenge authoring: draft validation and publishing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.services.authoring import (
    ALLOWED_TRACKS,
    AuthoringError,
    ChallengeDraft,
    blocking_issues,
    draft_from_payload,
    load_draft,
    publish_draft,
    validate_draft,
)

VALID_DESCRIPTION = (
    "# Sum Two Numbers\n\n"
    "Add two integers and return the result.\n\n"
    "## Your task\n\n"
    "Implement `add(a, b)` returning the sum.\n\n"
    "## Examples\n\n"
    "| a | b | result |\n"
    "|---|---|--------|\n"
    "| 1 | 2 | 3      |\n\n"
    "## Hints\n\n"
    "<details><summary>Hint 1</summary>\n\nUse the `+` operator.\n</details>\n"
)

VALID_STARTER = (
    'def add(a: int, b: int) -> int:\n'
    '    """Return the sum of a and b."""\n'
    "    # TODO: implement.\n"
    '    raise NotImplementedError\n'
)

VISIBLE = {
    "test_visible.py": (
        "from solution import add\n\n\ndef test_adds():\n    assert add(1, 2) == 3\n"
    )
}
HIDDEN = {
    "test_hidden.py": (
        "from solution import add\n\n\n"
        "def test_negatives():\n    assert add(-1, -1) == -2\n\n\n"
        "def test_zero():\n    assert add(0, 0) == 0\n"
    )
}


def valid_draft(**overrides: object) -> ChallengeDraft:
    base = ChallengeDraft(
        slug="sum-two-numbers",
        track="python-fundamentals",
        title="Sum Two Numbers",
        summary="Add two integers.",
        difficulty="beginner",
        level="junior",
        description=VALID_DESCRIPTION,
        starter_code=VALID_STARTER,
        visible_tests=dict(VISIBLE),
        hidden_tests=dict(HIDDEN),
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


# --- a good draft --------------------------------------------------------
def test_valid_draft_has_no_blocking_issues() -> None:
    assert blocking_issues(validate_draft(valid_draft())) == []


def test_derived_id_matches_directory_convention() -> None:
    """The loader requires id == '<track>-<slug>'."""
    assert valid_draft().challenge_id == "python-fundamentals-sum-two-numbers"


# --- identity ------------------------------------------------------------
@pytest.mark.parametrize("slug", ["Has Spaces", "UPPER", "trailing-", "-leading", "double--hyphen", ""])
def test_invalid_slugs_are_rejected(slug: str) -> None:
    issues = blocking_issues(validate_draft(valid_draft(slug=slug)))
    assert any(issue.field == "slug" for issue in issues)


@pytest.mark.parametrize("slug", ["sum", "sum-two-numbers", "lru-cache2", "a1-b2"])
def test_valid_slugs_are_accepted(slug: str) -> None:
    issues = blocking_issues(validate_draft(valid_draft(slug=slug)))
    assert not any(issue.field == "slug" for issue in issues)


def test_unknown_track_is_rejected() -> None:
    """A track outside the roadmap would break the roadmap view."""
    issues = blocking_issues(validate_draft(valid_draft(track="not-a-real-track")))
    assert any(issue.field == "track" for issue in issues)


def test_every_allowed_track_matches_the_roadmap() -> None:
    """An authoring track outside the roadmap would show no progress anywhere."""
    from app.services.roadmap import ROADMAP

    roadmap_tracks = {stage.id for stage in ROADMAP}
    assert set(ALLOWED_TRACKS) <= roadmap_tracks


# --- descriptive fields --------------------------------------------------
def test_missing_title_is_an_error() -> None:
    issues = blocking_issues(validate_draft(valid_draft(title="   ")))
    assert any(issue.field == "title" for issue in issues)


def test_missing_summary_is_an_error() -> None:
    issues = blocking_issues(validate_draft(valid_draft(summary="")))
    assert any(issue.field == "summary" for issue in issues)


def test_short_description_is_an_error() -> None:
    issues = blocking_issues(validate_draft(valid_draft(description="Too short.")))
    assert any(issue.field == "description" for issue in issues)


def test_invalid_difficulty_is_an_error() -> None:
    issues = blocking_issues(validate_draft(valid_draft(difficulty="impossible")))
    assert any(issue.field == "difficulty" for issue in issues)


def test_invalid_level_is_an_error() -> None:
    issues = blocking_issues(validate_draft(valid_draft(level="wizard")))
    assert any(issue.field == "level" for issue in issues)


# --- limits --------------------------------------------------------------
@pytest.mark.parametrize(
    ("field", "value"),
    [("points", -1), ("points", 5000), ("time_limit_ms", 10), ("memory_limit_mb", 1)],
)
def test_out_of_range_limits_are_errors(field: str, value: int) -> None:
    issues = blocking_issues(validate_draft(valid_draft(**{field: value})))
    assert any(issue.field == field for issue in issues)


# --- code and tests ------------------------------------------------------
def test_missing_starter_code_is_an_error() -> None:
    issues = blocking_issues(validate_draft(valid_draft(starter_code="")))
    assert any(issue.field == "starter_code" for issue in issues)


def test_missing_visible_tests_is_an_error() -> None:
    issues = blocking_issues(validate_draft(valid_draft(visible_tests={})))
    assert any(issue.field == "visible_tests" for issue in issues)


def test_missing_hidden_tests_is_an_error() -> None:
    """Hidden tests are what make grading meaningful."""
    issues = blocking_issues(validate_draft(valid_draft(hidden_tests={})))
    assert any(issue.field == "hidden_tests" for issue in issues)


def test_test_file_must_be_a_python_file() -> None:
    issues = blocking_issues(validate_draft(valid_draft(visible_tests={"test_bad.txt": "x"})))
    assert any(issue.field == "visible_tests" for issue in issues)


def test_test_file_must_use_the_test_prefix() -> None:
    """pytest would silently not collect a misnamed file."""
    issues = blocking_issues(validate_draft(valid_draft(visible_tests={"checks.py": "x = 1"})))
    assert any("test_" in issue.message for issue in issues)


def test_test_file_cannot_escape_the_directory() -> None:
    issues = blocking_issues(validate_draft(valid_draft(visible_tests={"../evil.py": "x"})))
    assert any(issue.field == "visible_tests" for issue in issues)


@pytest.mark.parametrize("module", ["requests", "numpy", "fastapi", "sqlalchemy", "docker"])
def test_unavailable_third_party_imports_are_rejected(module: str) -> None:
    """These would fail at run time in the sandbox; catch them at author time."""
    source = f"import {module}\n\n\ndef test_x():\n    assert True\n"
    issues = blocking_issues(validate_draft(valid_draft(visible_tests={"test_x.py": source})))
    assert any("sandbox" in issue.message for issue in issues)


def test_from_import_of_unavailable_module_is_rejected() -> None:
    source = "from fastapi import FastAPI\n\n\ndef test_x():\n    assert True\n"
    issues = blocking_issues(validate_draft(valid_draft(hidden_tests={"test_x.py": source})))
    assert any("sandbox" in issue.message for issue in issues)


def test_standard_library_imports_are_allowed() -> None:
    source = (
        "import json\nimport re\nfrom collections import Counter\n"
        "from solution import add\n\n\ndef test_x():\n    assert add(1, 1) == 2\n"
    )
    issues = blocking_issues(validate_draft(valid_draft(visible_tests={"test_x.py": source})))
    assert not [i for i in issues if "sandbox" in i.message]


def test_test_not_importing_solution_warns_but_does_not_block() -> None:
    issues = validate_draft(valid_draft(visible_tests={"test_x.py": "def test_x():\n    assert True\n"}))
    warnings = [i for i in issues if i.severity == "warning"]
    assert any("solution" in i.message for i in warnings)
    assert blocking_issues(issues) == []


def test_no_skills_warns_but_does_not_block() -> None:
    issues = validate_draft(valid_draft(skills=[]))
    assert blocking_issues(issues) == []
    assert any(issue.field == "skills" and issue.severity == "warning" for issue in issues)


def test_fewer_hidden_than_visible_tests_warns() -> None:
    """Hidden tests must outnumber visible ones to add real coverage."""
    many_visible = {
        "test_a.py": "from solution import add\n",
        "test_b.py": "from solution import add\n",
        "test_c.py": "from solution import add\n",
    }
    issues = validate_draft(valid_draft(visible_tests=many_visible))
    assert any(issue.severity == "warning" and "hidden" in issue.field for issue in issues)
    assert blocking_issues(issues) == []


# --- payload parsing -----------------------------------------------------
def test_payload_rejects_non_object() -> None:
    with pytest.raises(AuthoringError, match="JSON object"):
        draft_from_payload(["not", "an", "object"])


def test_payload_rejects_wrong_field_type() -> None:
    with pytest.raises(AuthoringError, match="must be a string"):
        draft_from_payload({"slug": "x", "title": 123})


def test_payload_rejects_non_numeric_int_field() -> None:
    with pytest.raises(AuthoringError, match="must be a number"):
        draft_from_payload({"slug": "x", "points": "lots"})


def test_payload_rejects_negative_points_gracefully() -> None:
    """A negative value is a validation problem, not a parse failure."""
    draft = draft_from_payload({"slug": "x", "points": -5})
    assert draft.points == -5


def test_payload_parses_test_maps() -> None:
    draft = draft_from_payload(
        {"slug": "x", "visible_tests": {"test_a.py": "x = 1"}, "skills": ["python.functions"]}
    )
    assert draft.visible_tests == {"test_a.py": "x = 1"}
    assert draft.skills == ["python.functions"]


def test_payload_rejects_non_string_test_source() -> None:
    with pytest.raises(AuthoringError, match="source text"):
        draft_from_payload({"slug": "x", "visible_tests": {"test_a.py": 42}})


def test_payload_rejects_non_list_tags() -> None:
    with pytest.raises(AuthoringError, match="list of strings"):
        draft_from_payload({"slug": "x", "tags": "strings"})


def test_payload_rejects_non_string_field() -> None:
    with pytest.raises(AuthoringError, match="must be a string"):
        draft_from_payload({"slug": "x", "summary": ["not", "a", "string"]})


# --- publishing ----------------------------------------------------------
def test_publish_writes_the_loader_format(tmp_path: Path) -> None:
    root = tmp_path / "challenges"
    root.mkdir()

    target = publish_draft(valid_draft(), root)

    assert (target / "metadata.json").is_file()
    assert (target / "description.md").is_file()
    assert (target / "starter" / "solution.py").is_file()
    assert (target / "tests" / "test_visible.py").is_file()
    assert (target / "tests" / "test_hidden.py").is_file()

    metadata = json.loads((target / "metadata.json").read_text())
    assert metadata["id"] == "python-fundamentals-sum-two-numbers"
    assert metadata["track"] == "python-fundamentals"
    assert metadata["entry_file"] == "solution.py"


def test_published_challenge_passes_the_real_loader(tmp_path: Path) -> None:
    """The strongest guarantee: what we write is what the catalogue can read."""
    from app.services.challenges import ChallengeRepository

    root = tmp_path / "challenges"
    root.mkdir()
    publish_draft(valid_draft(), root)

    repository = ChallengeRepository(root)
    loaded = repository.load_all(strict=True)

    assert repository.errors == []
    assert len(loaded) == 1
    assert loaded[0].id == "python-fundamentals-sum-two-numbers"
    assert loaded[0].visible_test_count == 1
    assert loaded[0].hidden_test_count == 1


def test_publish_refuses_an_invalid_draft(tmp_path: Path) -> None:
    root = tmp_path / "challenges"
    root.mkdir()

    with pytest.raises(AuthoringError, match="validation errors"):
        publish_draft(valid_draft(title=""), root)

    # Nothing was written.
    assert list(root.iterdir()) == []


def test_publish_refuses_to_overwrite_when_asked(tmp_path: Path) -> None:
    root = tmp_path / "challenges"
    root.mkdir()
    publish_draft(valid_draft(), root)

    with pytest.raises(AuthoringError, match="already exists"):
        publish_draft(valid_draft(title="Different"), root, overwrite=False)


def test_publish_can_overwrite(tmp_path: Path) -> None:
    root = tmp_path / "challenges"
    root.mkdir()
    publish_draft(valid_draft(), root)
    publish_draft(valid_draft(title="Updated Title"), root)

    metadata = json.loads(
        (root / "python-fundamentals" / "sum-two-numbers" / "metadata.json").read_text()
    )
    assert metadata["title"] == "Updated Title"


def test_publish_leaves_no_staging_directory(tmp_path: Path) -> None:
    """A failed or successful write must not litter the content directory."""
    root = tmp_path / "challenges"
    root.mkdir()
    publish_draft(valid_draft(), root)

    leftovers = [p for p in (root / "python-fundamentals").iterdir() if p.name.startswith(".")]
    assert leftovers == []


def test_no_duplicate_hidden_test_filename_collision(tmp_path: Path) -> None:
    """A visible and hidden file cannot share a name."""
    root = tmp_path / "challenges"
    root.mkdir()
    clash = valid_draft(
        visible_tests={"test_same.py": "from solution import add\n"},
        hidden_tests={"test_same.py": "from solution import add\n"},
    )
    publish_draft(clash, root)

    written = sorted(p.name for p in (root / "python-fundamentals" / "sum-two-numbers" / "tests").iterdir())
    assert written == ["test_same.py"]


# --- round trip ----------------------------------------------------------
def test_draft_round_trips_through_disk(tmp_path: Path) -> None:
    root = tmp_path / "challenges"
    root.mkdir()
    original = valid_draft(skills=["python.functions"], tags=["basics"], module="Arithmetic")
    publish_draft(original, root)

    reloaded = load_draft(root, "python-fundamentals", "sum-two-numbers")

    assert reloaded is not None
    assert reloaded.title == original.title
    assert reloaded.skills == ["python.functions"]
    assert reloaded.tags == ["basics"]
    assert reloaded.module == "Arithmetic"
    assert reloaded.starter_code == original.starter_code
    assert reloaded.description == original.description
    assert reloaded.visible_tests == original.visible_tests
    assert reloaded.hidden_tests == original.hidden_tests


def test_load_draft_returns_none_for_unknown(tmp_path: Path) -> None:
    assert load_draft(tmp_path, "python-fundamentals", "nope") is None


def test_round_tripped_draft_stays_valid(tmp_path: Path) -> None:
    """Editing a published challenge must not introduce validation errors."""
    root = tmp_path / "challenges"
    root.mkdir()
    publish_draft(valid_draft(), root)

    reloaded = load_draft(root, "python-fundamentals", "sum-two-numbers")
    assert reloaded is not None
    assert blocking_issues(validate_draft(reloaded)) == []
