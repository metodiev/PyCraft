"""Skill graph: nodes, dependencies and mastery derived from real progress."""

from __future__ import annotations

import pytest
from app.models import ProgressStatus
from app.services.roadmap import ROADMAP
from app.services.skill_graph import build_graph
from httpx import AsyncClient

CHALLENGE = "python-fundamentals-hello-world"
SOLUTION = {"solution.py": "def greet(name):\n    return f'Hello, {name}!'\n"}
GRAPH = "/api/v1/skill-graph"


class FakeChallenge:
    """Minimal stand-in for a LoadedChallenge."""

    def __init__(self, challenge_id: str, track: str, skills: list[str]) -> None:
        self.id = challenge_id
        self.track = track
        self.skills = skills


class FakeProgress:
    def __init__(self, status: ProgressStatus) -> None:
        self.status = status


class FakeSkill:
    def __init__(self, skill: str, mastery: int = 0, xp: int = 0) -> None:
        self.skill = skill
        self.mastery = mastery
        self.xp = xp


# --- pure graph construction ---------------------------------------------
def test_empty_record_produces_the_roadmap_skills() -> None:
    """Even with no progress, the graph shows what the journey contains."""
    graph = build_graph(challenges=[], skill_rows={}, progress_rows={})

    node_ids = {node.id for node in graph.nodes}
    assert "python.fundamentals" in node_ids
    assert "architecture" in node_ids
    assert graph.mastered == 0
    assert graph.in_progress == 0


def test_every_roadmap_skill_appears_as_a_node() -> None:
    graph = build_graph(challenges=[], skill_rows={}, progress_rows={})
    node_ids = {node.id for node in graph.nodes}

    for stage in ROADMAP:
        assert stage.skill in node_ids, f"missing node for {stage.skill}"


def test_edges_follow_roadmap_dependencies() -> None:
    """The graph is a graph, not a list: prerequisites must be visible."""
    graph = build_graph(challenges=[], skill_rows={}, progress_rows={})

    pairs = {(edge.source, edge.target) for edge in graph.edges}
    # Each stage declares its prerequisite; the edge must follow that.
    assert ("python.fundamentals", "python.professional") in pairs
    assert ("testing", "web") in pairs
    assert ("web", "databases") in pairs
    assert ("distributed", "system_design") in pairs
    assert ("system_design", "architecture") in pairs
    # One edge per declared `requires` in the roadmap.
    expected = sum(len(stage.requires) for stage in ROADMAP)
    assert len(graph.edges) == expected


def test_edges_match_every_declared_requirement() -> None:
    """No stage may be missing from the graph by accident."""
    from app.services.roadmap import STAGES_BY_ID

    graph = build_graph(challenges=[], skill_rows={}, progress_rows={})
    actual = {(edge.source, edge.target) for edge in graph.edges}

    for stage in ROADMAP:
        for required_id in stage.requires:
            required = STAGES_BY_ID[required_id]
            if required.skill == stage.skill:
                continue
            assert (required.skill, stage.skill) in actual, (
                f"missing edge {required.skill} -> {stage.skill}"
            )


def test_challenge_counts_are_aggregated_per_skill() -> None:
    challenges = [
        FakeChallenge("a-1", "python-fundamentals", ["python.basics", "python.fundamentals"]),
        FakeChallenge("a-2", "python-fundamentals", ["python.basics"]),
    ]
    graph = build_graph(challenges=challenges, skill_rows={}, progress_rows={})
    basics = next(node for node in graph.nodes if node.id == "python.basics")

    assert basics.challenges_total == 2
    assert basics.challenges_completed == 0
    assert basics.tracks == ["python-fundamentals"]


def test_completed_challenges_now_contribute_mastery() -> None:
    challenges = [
        FakeChallenge("a-1", "python-fundamentals", ["python.basics"]),
        FakeChallenge("a-2", "python-fundamentals", ["python.basics"]),
    ]
    progress = {"a-1": FakeProgress(ProgressStatus.COMPLETED)}

    graph = build_graph(challenges=challenges, skill_rows={}, progress_rows=progress)  # type: ignore[arg-type]
    basics = next(node for node in graph.nodes if node.id == "python.basics")

    assert basics.challenges_completed == 1
    # One of two completed falls back to a 50% ratio.
    assert basics.mastery == 50
    assert basics.status == "in_progress"


def test_recorded_mastery_wins_over_the_ratio() -> None:
    """The stored value is authoritative once a submission has been graded."""
    challenges = [FakeChallenge("a-1", "python-fundamentals", ["python.basics"])]
    graph = build_graph(
        challenges=challenges,
        skill_rows={"python.basics": FakeSkill("python.basics", mastery=90, xp=40)},  # type: ignore[arg-type]
        progress_rows={},
    )
    basics = next(node for node in graph.nodes if node.id == "python.basics")

    assert basics.mastery == 90
    assert basics.xp == 40
    assert basics.status == "mastered"


def test_status_thresholds() -> None:
    """Mastery alone decides the state, once the skill has content."""
    challenges = [FakeChallenge("a-1", "python-fundamentals", ["python.fundamentals"])]

    cases = [
        (0, "available"),
        (30, "in_progress"),
        (69, "in_progress"),
        (70, "mastered"),
        (100, "mastered"),
    ]
    for mastery, expected in cases:
        graph = build_graph(
            challenges=challenges,
            skill_rows={"python.fundamentals": FakeSkill("python.fundamentals", mastery=mastery)},  # type: ignore[arg-type]
            progress_rows={},
        )
        node = next(n for n in graph.nodes if n.id == "python.fundamentals")
        assert node.status == expected, f"mastery {mastery} should be {expected}"


def test_zero_mastery_without_content_is_unavailable() -> None:
    """A stage with no challenges reads as 'coming soon' rather than 'start here'."""
    graph = build_graph(challenges=[], skill_rows={}, progress_rows={})
    # 'architecture' is a roadmap skill that no shipped challenge covers yet.
    node = next(n for n in graph.nodes if n.id == "architecture")

    assert node.challenges_total == 0
    assert node.status == "unavailable"


def test_skill_without_content_is_marked_unavailable() -> None:
    """A stage with no challenges yet should read as 'coming soon', not 'start here'."""
    graph = build_graph(challenges=[], skill_rows={}, progress_rows={})
    architecture = next(node for node in graph.nodes if node.id == "architecture")

    assert architecture.challenges_total == 0
    assert architecture.status == "unavailable"


def test_node_order_follows_the_roadmap() -> None:
    graph = build_graph(challenges=[], skill_rows={}, progress_rows={})
    ids = [node.id for node in graph.nodes]

    assert ids.index("python.fundamentals") < ids.index("python.professional")
    assert ids.index("python.professional") < ids.index("testing")
    assert ids.index("testing") < ids.index("architecture")


def test_off_roadmap_skills_are_still_included() -> None:
    """A challenge may declare a skill no stage covers; it must not vanish."""
    challenges = [FakeChallenge("a-1", "python-fundamentals", ["python.custom.skill"])]
    graph = build_graph(challenges=challenges, skill_rows={}, progress_rows={})

    node = next(n for n in graph.nodes if n.id == "python.custom.skill")
    assert node.challenges_total == 1
    # Falls back to a humanised id.
    assert node.label == "Python Custom Skill"


def test_locking_requires_the_prerequisite_to_have_content() -> None:
    """A prerequisite with no challenges must not lock its dependants."""
    graph = build_graph(challenges=[], skill_rows={}, progress_rows={})
    # Every node is reachable when nothing has content yet.
    assert all(node.unlocked for node in graph.nodes)


def test_dependants_lock_until_the_prerequisite_is_started() -> None:
    challenges = [
        FakeChallenge("f-1", "python-fundamentals", ["python.fundamentals"]),
        FakeChallenge("p-1", "python-professional", ["python.professional"]),
    ]
    graph = build_graph(challenges=challenges, skill_rows={}, progress_rows={})

    professional = next(n for n in graph.nodes if n.id == "python.professional")
    assert professional.unlocked is False

    # Once the prerequisite is started, it unlocks.
    started = {"f-1": FakeProgress(ProgressStatus.COMPLETED)}
    graph = build_graph(challenges=challenges, skill_rows={}, progress_rows=started)  # type: ignore[arg-type]
    professional = next(n for n in graph.nodes if n.id == "python.professional")
    assert professional.unlocked is True


def test_graph_reports_summary_counts() -> None:
    challenges = [FakeChallenge("a-1", "python-fundamentals", ["python.basics"])]
    graph = build_graph(
        challenges=challenges,
        skill_rows={
            "python.basics": FakeSkill("python.basics", mastery=100),  # type: ignore[arg-type]
            "testing": FakeSkill("testing", mastery=40),  # type: ignore[arg-type]
        },
        progress_rows={},
    )
    assert graph.mastered == 1
    assert graph.in_progress == 1


# --- API -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_skill_graph_requires_authentication(anon_client: AsyncClient) -> None:
    assert (await anon_client.get(GRAPH)).status_code == 401


@pytest.mark.asyncio
async def test_skill_graph_returns_nodes_and_edges(client: AsyncClient) -> None:
    response = await client.get(GRAPH)
    assert response.status_code == 200

    body = response.json()
    assert body["total"] > 0
    assert len(body["nodes"]) == body["total"]
    assert len(body["edges"]) > 0

    node = body["nodes"][0]
    for key in ("id", "label", "mastery", "status", "depends_on", "unlocked"):
        assert key in node


@pytest.mark.asyncio
async def test_solving_a_challenge_moves_its_skill(client: AsyncClient) -> None:
    before = (await client.get(GRAPH)).json()
    basics_before = next(n for n in before["nodes"] if n["id"] == "python.basics")
    assert basics_before["mastery"] == 0
    # The fixture challenge declares python.basics, so it has content.
    assert basics_before["challenges_total"] == 1

    await client.post(f"/api/v1/challenges/{CHALLENGE}/submit", json={"files": SOLUTION})

    after = (await client.get(GRAPH)).json()
    basics_after = next(n for n in after["nodes"] if n["id"] == "python.basics")

    assert basics_after["mastery"] > 0
    assert basics_after["challenges_completed"] == 1
    assert basics_after["status"] in {"in_progress", "mastered"}


@pytest.mark.asyncio
async def test_progress_is_per_learner(
    anon_client: AsyncClient, client: AsyncClient, second_client: AsyncClient
) -> None:
    """One learner's mastery must not appear in another's graph."""
    from tests.conftest import register_account

    await client.post(f"/api/v1/challenges/{CHALLENGE}/submit", json={"files": SOLUTION})

    other = await register_account(second_client, email="other@example.com")
    second_client.headers["Authorization"] = f"Bearer {other.access_token}"

    mine = (await client.get(GRAPH)).json()
    theirs = (await second_client.get(GRAPH)).json()

    my_basics = next(n for n in mine["nodes"] if n["id"] == "python.basics")
    their_basics = next(n for n in theirs["nodes"] if n["id"] == "python.basics")

    assert my_basics["mastery"] > 0
    assert their_basics["mastery"] == 0


@pytest.mark.asyncio
async def test_graph_edges_reference_real_nodes(client: AsyncClient) -> None:
    """Dangling edges would break the visualisation."""
    body = (await client.get(GRAPH)).json()
    node_ids = {node["id"] for node in body["nodes"]}

    for edge in body["edges"]:
        assert edge["source"] in node_ids
        assert edge["target"] in node_ids


@pytest.mark.asyncio
async def test_graph_contains_every_roadmap_skill(client: AsyncClient) -> None:
    body = (await client.get(GRAPH)).json()
    node_ids = {node["id"] for node in body["nodes"]}

    for stage in ROADMAP:
        assert stage.skill in node_ids
