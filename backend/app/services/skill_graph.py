"""Skill graph.

The spec asks for a *graph* rather than a linear list, so learners can see which
skills they have demonstrated and what each one unlocks.

Skills come from two places and are joined here:

* **Challenge metadata** declares which skills a challenge demonstrates.
* **The roadmap** declares which skill each stage develops and what it depends
  on.

The graph is therefore derived from content, not hand-maintained, so adding a
challenge cannot leave the graph out of date.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChallengeProgress, ProgressStatus, SkillProgress, User
from app.services.roadmap import ROADMAP, STAGES_BY_ID, RoadmapStage


@dataclass(slots=True)
class SkillNode:
    """One node in the skill graph, with the learner's standing on it."""

    id: str
    label: str
    description: str
    level: str
    # 0-100, the learner's demonstrated mastery.
    mastery: int = 0
    xp: int = 0
    challenges_total: int = 0
    challenges_completed: int = 0
    # Skill ids that should be developed first.
    depends_on: list[str] = field(default_factory=list)
    # Whether the prerequisites are satisfied (at least started).
    unlocked: bool = True
    # Tracks that contribute to this skill.
    tracks: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        """Coarse state, so the UI can colour the node without extra logic."""
        if self.mastery >= 70:
            return "mastered"
        if self.challenges_completed > 0 or self.mastery > 0:
            return "in_progress"
        if self.challenges_total == 0:
            return "unavailable"
        return "available"


@dataclass(slots=True)
class SkillEdge:
    """A dependency between two skills."""

    source: str
    target: str


@dataclass(slots=True)
class SkillGraph:
    nodes: list[SkillNode]
    edges: list[SkillEdge]

    @property
    def mastered(self) -> int:
        return sum(1 for node in self.nodes if node.status == "mastered")

    @property
    def in_progress(self) -> int:
        return sum(1 for node in self.nodes if node.status == "in_progress")


def build_graph(
    *,
    challenges: list,
    skill_rows: dict[str, SkillProgress],
    progress_rows: dict[str, ChallengeProgress],
) -> SkillGraph:
    """Assemble the graph from content plus the learner's record.

    Pure function over already-loaded data, so it is cheap to call and easy to
    test without a database.
    """
    # --- aggregate challenge metadata per skill ---------------------------
    totals: dict[str, int] = {}
    completed: dict[str, int] = {}
    tracks_by_skill: dict[str, set[str]] = {}

    for challenge in challenges:
        for skill in challenge.skills:
            totals[skill] = totals.get(skill, 0) + 1
            tracks_by_skill.setdefault(skill, set()).add(challenge.track)
            row = progress_rows.get(challenge.id)
            if row is not None and row.status is ProgressStatus.COMPLETED:
                completed[skill] = completed.get(skill, 0) + 1

    # --- roadmap stages are skill nodes in their own right ----------------
    stage_skills: dict[str, RoadmapStage] = {stage.skill: stage for stage in ROADMAP}

    node_ids = sorted(set(totals) | set(stage_skills) | set(skill_rows))

    nodes: list[SkillNode] = []
    edges: list[SkillEdge] = []

    for skill_id in node_ids:
        stage = stage_skills.get(skill_id)
        row = skill_rows.get(skill_id)

        total = totals.get(skill_id, 0)
        done = completed.get(skill_id, 0)

        # Mastery prefers the recorded value, falling back to completion ratio
        # so a freshly-solved challenge shows progress before the next recalc.
        if row is not None and row.mastery > 0:
            mastery = row.mastery
        elif total:
            mastery = round(done / total * 100)
        else:
            mastery = 0

        depends_on: list[str] = []
        if stage is not None:
            # A stage depends on the skill developed by each stage it requires.
            for required_stage_id in stage.requires:
                required_stage = STAGES_BY_ID.get(required_stage_id)
                if required_stage is not None and required_stage.skill != skill_id:
                    depends_on.append(required_stage.skill)

        nodes.append(
            SkillNode(
                id=skill_id,
                label=_label_for(skill_id, stage),
                description=stage.description if stage else "",
                level=stage.level if stage else "junior",
                mastery=mastery,
                xp=row.xp if row else 0,
                challenges_total=total,
                challenges_completed=done,
                depends_on=depends_on,
                tracks=sorted(tracks_by_skill.get(skill_id, set())),
            )
        )

    # --- resolve unlock state, then emit edges ---------------------------
    by_id = {node.id: node for node in nodes}
    for node in nodes:
        for dependency in node.depends_on:
            parent = by_id.get(dependency)
            # A prerequisite is satisfied once it has been started at all;
            # demanding mastery would make the graph frustrating to advance.
            not_started = (
                parent is not None
                and parent.mastery == 0
                and parent.challenges_completed == 0
            )
            # Only lock when the prerequisite actually has content to do.
            if not_started and parent is not None and parent.challenges_total > 0:
                node.unlocked = False
            edges.append(SkillEdge(source=dependency, target=node.id))

    # Present in roadmap order, then alphabetically for anything off-roadmap.
    order = {stage.skill: index for index, stage in enumerate(ROADMAP)}
    nodes.sort(key=lambda node: (order.get(node.id, len(order)), node.id))

    return SkillGraph(nodes=nodes, edges=edges)


async def load_graph(session: AsyncSession, user: User, challenges: list) -> SkillGraph:
    """Load the learner's record and build their graph."""
    skill_rows = {
        row.skill: row
        for row in (
            await session.scalars(select(SkillProgress).where(SkillProgress.user_id == user.id))
        ).all()
    }
    progress_rows = {
        row.challenge_id: row
        for row in (
            await session.scalars(
                select(ChallengeProgress).where(ChallengeProgress.user_id == user.id)
            )
        ).all()
    }

    return build_graph(
        challenges=challenges, skill_rows=skill_rows, progress_rows=progress_rows
    )


def _label_for(skill_id: str, stage: RoadmapStage | None) -> str:
    if stage is not None:
        return stage.title
    return skill_id.replace(".", " ").replace("_", " ").title()
