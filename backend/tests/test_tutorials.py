"""Tutorial loading: format validation, discovery and reading-time estimation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.services.tutorials import (
    TutorialFormatError,
    TutorialNotFoundError,
    TutorialRepository,
)
from tests.conftest import write_tutorial


def test_loads_valid_tutorial(tutorials_dir: Path) -> None:
    repository = TutorialRepository(tutorials_dir)
    loaded = repository.load_all(strict=True)

    assert len(loaded) == 1
    tutorial = loaded[0]
    assert tutorial.id == "python-fundamentals-test-tutorial"
    assert tutorial.title == "Test Tutorial"
    assert tutorial.track == "python-fundamentals"
    assert tutorial.difficulty == "beginner"
    assert tutorial.reading_minutes == 5
    assert "Read this" in tutorial.content


def test_discovery_ignores_a_directory_without_metadata(tutorials_dir: Path) -> None:
    stray = tutorials_dir / "python-fundamentals" / "not-a-tutorial"
    stray.mkdir()
    (stray / "tutorial.md").write_text("# Orphan\n", encoding="utf-8")

    loaded = TutorialRepository(tutorials_dir).load_all(strict=True)
    assert [t.id for t in loaded] == ["python-fundamentals-test-tutorial"]


def test_a_missing_tutorials_directory_is_not_an_error(tmp_path: Path) -> None:
    repository = TutorialRepository(tmp_path / "absent")

    assert repository.load_all(strict=True) == []
    assert repository.all() == []


def test_missing_required_field_is_reported(tmp_path: Path) -> None:
    root = tmp_path / "tutorials"
    root.mkdir()
    path = write_tutorial(root)
    metadata = json.loads((path / "metadata.json").read_text())
    del metadata["title"]
    (path / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(TutorialFormatError, match="title"):
        TutorialRepository(root).load_all(strict=True)


def test_id_must_match_the_directory_name(tmp_path: Path) -> None:
    root = tmp_path / "tutorials"
    root.mkdir()
    write_tutorial(root, slug="real-slug", tutorial_id="python-fundamentals-other-slug")

    with pytest.raises(TutorialFormatError, match="does not match directory"):
        TutorialRepository(root).load_all(strict=True)


def test_track_must_match_the_directory(tmp_path: Path) -> None:
    root = tmp_path / "tutorials"
    root.mkdir()
    write_tutorial(
        root,
        track="python-fundamentals",
        slug="misplaced",
        tutorial_id="databases-misplaced",
    )

    with pytest.raises(TutorialFormatError, match="does not match directory"):
        TutorialRepository(root).load_all(strict=True)


def test_unknown_track_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "tutorials"
    root.mkdir()
    write_tutorial(root, track="not-a-track", slug="x", tutorial_id="not-a-track-x")

    with pytest.raises(TutorialFormatError, match="unknown track"):
        TutorialRepository(root).load_all(strict=True)


def test_unknown_difficulty_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "tutorials"
    root.mkdir()
    write_tutorial(root, difficulty="impossible")

    with pytest.raises(TutorialFormatError, match="difficulty"):
        TutorialRepository(root).load_all(strict=True)


def test_an_empty_article_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "tutorials"
    root.mkdir()
    write_tutorial(root, body="   \n\n")

    with pytest.raises(TutorialFormatError, match="empty"):
        TutorialRepository(root).load_all(strict=True)


def test_a_missing_article_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "tutorials"
    root.mkdir()
    path = write_tutorial(root)
    (path / "tutorial.md").unlink()

    with pytest.raises(TutorialFormatError, match=r"tutorial\.md"):
        TutorialRepository(root).load_all(strict=True)


def test_reading_time_is_estimated_when_not_declared(tmp_path: Path) -> None:
    root = tmp_path / "tutorials"
    root.mkdir()
    # 400 words at 200 wpm is 2 minutes.
    write_tutorial(root, extra_metadata={"reading_minutes": None}, body="# T\n\n" + "word " * 400)

    tutorial = TutorialRepository(root).load_all(strict=True)[0]
    assert tutorial.reading_minutes == 2


def test_a_declared_reading_time_wins(tmp_path: Path) -> None:
    root = tmp_path / "tutorials"
    root.mkdir()
    write_tutorial(root, extra_metadata={"reading_minutes": 42}, body="# T\n\n" + "word " * 400)

    assert TutorialRepository(root).load_all(strict=True)[0].reading_minutes == 42


def test_invalid_content_is_skipped_and_reported(tutorials_dir: Path) -> None:
    """One bad file must not hide the rest of the catalogue."""
    broken = tutorials_dir / "python-fundamentals" / "broken"
    broken.mkdir()
    (broken / "metadata.json").write_text("{not json", encoding="utf-8")

    repository = TutorialRepository(tutorials_dir)
    loaded = repository.load_all()

    assert [t.id for t in loaded] == ["python-fundamentals-test-tutorial"]
    assert len(repository.errors) == 1
    assert "broken" in repository.errors[0]


def test_ordering_is_by_track_then_order_index(tmp_path: Path) -> None:
    root = tmp_path / "tutorials"
    root.mkdir()
    write_tutorial(root, slug="second", tutorial_id="python-fundamentals-second",
                   extra_metadata={"order_index": 2})
    write_tutorial(root, slug="first", tutorial_id="python-fundamentals-first",
                   extra_metadata={"order_index": 1})
    write_tutorial(root, track="testing-quality", slug="other",
                   tutorial_id="testing-quality-other",
                   extra_metadata={"order_index": 1})

    ids = [t.id for t in TutorialRepository(root).load_all(strict=True)]

    assert ids == [
        "python-fundamentals-first",
        "python-fundamentals-second",
        "testing-quality-other",
    ]


def test_get_raises_for_an_unknown_id(tutorials_dir: Path) -> None:
    repository = TutorialRepository(tutorials_dir)
    repository.load_all(strict=True)

    with pytest.raises(TutorialNotFoundError):
        repository.get("python-fundamentals-nope")


def test_by_track_and_total_reading_minutes(tutorials_dir: Path) -> None:
    write_tutorial(
        tutorials_dir,
        track="testing-quality",
        slug="other",
        tutorial_id="testing-quality-other",
        extra_metadata={"reading_minutes": 3},
    )
    repository = TutorialRepository(tutorials_dir)
    repository.load_all(strict=True)

    assert [t.id for t in repository.by_track("testing-quality")] == ["testing-quality-other"]
    assert repository.total_reading_minutes == 8
