/**
 * Challenge catalogue — grouped by track, with completion state.
 */

import { Link } from "react-router-dom";
import { useMemo } from "react";
import { api } from "../api/client";
import type { ChallengeSummary } from "../api/client";
import { Badge, Card, DifficultyBadge, EmptyState, Notice, ProgressBar, Skeleton } from "../components";
import { useApi } from "../hooks/useApi";
import "./challenges.css";

export function ChallengeList() {
  const { data, error, loading, reload } = useApi(() => api.listChallenges(), []);

  const grouped = useMemo(() => groupByTrack(data ?? []), [data]);

  if (loading) return <ListSkeleton />;
  if (error !== null) {
    return (
      <Notice tone="danger">
        {error}{" "}
        <button className="link-button" onClick={reload}>
          Retry
        </button>
      </Notice>
    );
  }
  if (data === null || data.length === 0) {
    return <EmptyState title="No challenges available" hint="Add content under challenges/ and restart the API." />;
  }

  return (
    <div className="challenge-list">
      <header className="list-head">
        <h1>Challenges</h1>
        <p className="list-sub">
          {data.filter((challenge) => challenge.completed).length} of {data.length} complete
        </p>
      </header>

      {grouped.map(([track, challenges]) => (
        <Card key={track} className="track-card">
          <header className="track-head">
            <h2 className="track-title">{formatTrack(track)}</h2>
            <Badge>
              {challenges.filter((c) => c.completed).length}/{challenges.length}
            </Badge>
          </header>
          <div className="challenge-grid">
            {challenges.map((challenge) => (
              <ChallengeCard key={challenge.id} challenge={challenge} />
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}

function ChallengeCard({ challenge }: { challenge: ChallengeSummary }) {
  return (
    <Link to={`/challenges/${challenge.id}`} className="challenge-card" data-completed={challenge.completed}>
      <div className="challenge-card-head">
        <DifficultyBadge difficulty={challenge.difficulty} />
        {challenge.completed ? (
          <span className="done-mark" title="Completed">
            ✓
          </span>
        ) : (
          <span className="points mono">{challenge.points} XP</span>
        )}
      </div>

      <h3 className="challenge-card-title">{challenge.title}</h3>
      <p className="challenge-card-summary">{challenge.summary}</p>

      <footer className="challenge-card-foot">
        <span className="module-name">{challenge.module}</span>
        <span className="challenge-card-score mono">
          {challenge.completed ? `${challenge.best_score}/100` : `${challenge.visible_test_count} tests`}
        </span>
      </footer>

      {challenge.best_score > 0 && !challenge.completed && (
        <ProgressBar value={challenge.best_score} showValue={false} tone="warning" />
      )}
    </Link>
  );
}

function groupByTrack(challenges: ChallengeSummary[]): Array<[string, ChallengeSummary[]]> {
  const groups = new Map<string, ChallengeSummary[]>();
  for (const challenge of challenges) {
    const existing = groups.get(challenge.track);
    if (existing === undefined) {
      groups.set(challenge.track, [challenge]);
    } else {
      existing.push(challenge);
    }
  }
  return [...groups.entries()];
}

function formatTrack(track: string): string {
  return track
    .split("-")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function ListSkeleton() {
  return (
    <div className="challenge-list">
      <Card>
        <Skeleton height="1.5rem" width="200px" />
        <div style={{ height: "var(--space-4)" }} />
        <Skeleton height="180px" />
      </Card>
    </div>
  );
}
