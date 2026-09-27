"""Challenge loading: format validation and the visible/hidden split."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.services.challenges import (
    ChallengeFormatError,
    ChallengeNotFoundError,
    ChallengeRepository,
)
from tests.conftest import write_challenge


def test_loads_valid_challenge(challenges_dir: Path) -> None:
    repository = ChallengeRepository(challenges_dir)
    loaded = repository.load_all(strict=True)

    assert len(loaded) == 1
    challenge = loaded[0]
    assert challenge.id == "python-fundamentals-hello-world"
    assert challenge.title == "Hello World"
    assert challenge.difficulty == "beginner"
    assert challenge.points == 50
    assert challenge.entry_file == "solution.py"
    assert "def greet" in challenge.files.starter
    assert "greet" in challenge.files.description or challenge.files.description


def test_separates_visible_and_hidden_tests(challenges_dir: Path) -> None:
    repository = ChallengeRepository(challenges_dir)
    challenge = repository.load_all(strict=True)[0]

    assert set(challenge.files.visible_tests) == {"test_visible.py"}
    assert set(challenge.files.hidden_tests) == {"test_hidden.py"}
    assert challenge.visible_test_count == 1
    assert challenge.hidden_test_count == 1


def test_multiple_hidden_files_are_all_hidden(challenges_dir: Path) -> None:
    path = challenges_dir / "python-fundamentals" / "hello-world"
    (path / "tests" / "test_hidden_edge.py").write_text("def test_x(): pass\n", encoding="utf-8")

    challenge = ChallengeRepository(challenges_dir).load_all(strict=True)[0]
    assert set(challenge.files.hidden_tests) == {"test_hidden.py", "test_hidden_edge.py"}
    assert set(challenge.files.visible_tests) == {"test_visible.py"}


def test_missing_required_field_is_reported(tmp_path: Path) -> None:
    root = tmp_path / "challenges"
    root.mkdir()
    path = write_challenge(root)
    metadata = json.loads((path / "metadata.json").read_text())
    del metadata["title"]
    (path / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    repository = ChallengeRepository(root)
    with pytest.raises(ChallengeFormatError, match="title"):
        repository.load_all(strict=True)


def test_invalid_challenges_are_skipped_without_strict_mode(tmp_path: Path) -> None:
    root = tmp_path / "challenges"
    root.mkdir()
    path = write_challenge(root)
    (path / "description.md").unlink()

    repository = ChallengeRepository(root)
    assert repository.load_all() == []
    assert len(repository.errors) == 1
    assert "description.md" in repository.errors[0]


def test_rejects_starter_missing(tmp_path: Path) -> None:
    root = tmp_path / "challenges"
    root.mkdir()
    path = write_challenge(root)
    (path / "starter" / "solution.py").unlink()

    with pytest.raises(ChallengeFormatError, match="starter"):
        ChallengeRepository(root).load_all(strict=True)


def test_rejects_challenge_without_hidden_tests(tmp_path: Path) -> None:
    root = tmp_path / "challenges"
    root.mkdir()
    path = write_challenge(root)
    (path / "tests" / "test_hidden.py").unlink()

    with pytest.raises(ChallengeFormatError, match="hidden"):
        ChallengeRepository(root).load_all(strict=True)


def test_rejects_id_that_does_not_match_directory(tmp_path: Path) -> None:
    root = tmp_path / "challenges"
    root.mkdir()
    path = write_challenge(root)
    metadata = json.loads((path / "metadata.json").read_text())
    metadata["id"] = "python-fundamentals-something-else"
    (path / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ChallengeFormatError, match="directory name"):
        ChallengeRepository(root).load_all(strict=True)


def test_rejects_track_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "challenges"
    root.mkdir()
    path = write_challenge(root)
    metadata = json.loads((path / "metadata.json").read_text())
    metadata["track"] = "wrong-track"
    (path / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ChallengeFormatError, match="does not match directory"):
        ChallengeRepository(root).load_all(strict=True)


def test_get_unknown_challenge_raises(challenges_dir: Path) -> None:
    repository = ChallengeRepository(challenges_dir)
    repository.load_all(strict=True)

    with pytest.raises(ChallengeNotFoundError):
        repository.get("does-not-exist")


def test_all_returns_roadmap_order(tmp_path: Path) -> None:
    root = tmp_path / "challenges"
    root.mkdir()
    write_challenge(root, track="aaa", slug="second", challenge_id="aaa-second", extra_metadata={"order_index": 2})
    write_challenge(root, track="aaa", slug="first", challenge_id="aaa-first", extra_metadata={"order_index": 1})
    write_challenge(root, track="bbb", slug="other", challenge_id="bbb-other", extra_metadata={"order_index": 1})

    repository = ChallengeRepository(root)
    repository.load_all(strict=True)

    assert repository.slugs() == ["aaa-first", "aaa-second", "bbb-other"]


def test_missing_content_directory_is_not_fatal(tmp_path: Path) -> None:
    repository = ChallengeRepository(tmp_path / "nope")
    assert repository.load_all() == []
    assert repository.all() == []
