/**
 * Roadmap — the engineering progression from fundamentals to principal engineer.
 */

import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { RoadmapStage } from "../api/client";
import { Badge, Card, Notice, ProgressBar, Skeleton } from "../components";
import { useApi } from "../hooks/useApi";
import { LEVEL_ORDER } from "../lib/levels";
import "./roadmap.css";

export function RoadmapPage() {
  const { data, error, loading, reload } = useApi(() => api.getRoadmap(), []);

  if (loading) return <RoadmapSkeleton />;
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
  if (data === null) return null;

  const withContent = data.filter((stage) => stage.total_challenges > 0).length;

  return (
    <div className="roadmap-page">
      <header className="roadmap-head">
        <h1>Engineering roadmap</h1>
        <p className="roadmap-sub">
          {withContent} of {data.length} stages have challenges available today. Completion is
          earned by passing tests, never by marking a lesson read.
        </p>
      </header>

      <ol className="roadmap-track">
        {data.map((stage, index) => (
          <RoadmapNode key={stage.id} stage={stage} index={index} wouldBeLocked={false} />
        ))}
      </ol>
    </div>
  );
}

function RoadmapNode({
  stage,
  index,
  wouldBeLocked,
}: {
  stage: RoadmapStage;
  index: number;
  wouldBeLocked: boolean;
}) {
  const levelLabel =
    LEVEL_ORDER.find((level) => level.id === stage.level)?.label ?? stage.level;
  const status = stage.total_challenges === 0 ? "empty" : stage.progress_pct === 100 ? "done" : "active";

  return (
    <li className="roadmap-node" data-status={status}>
      <div className="node-rail" aria-hidden="true">
        {index > 0 && <span className="rail-line rail-top" />}
        <span className="rail-dot" />
        {index < 12 && <span className="rail-line rail-bottom" />}
      </div>

      <Card className="node-card">
        <div className="node-head">
          <div>
            <h2 className="node-title">{stage.title}</h2>
            <span className="node-level">{levelLabel}</span>
          </div>
          {status === "done" ? (
            <Badge tone="success">Complete</Badge>
          ) : stage.total_challenges === 0 ? (
            <Badge>Coming soon</Badge>
          ) : (
            <Badge tone="accent">
              {stage.completed_challenges}/{stage.total_challenges}
            </Badge>
          )}
        </div>

        <p className="node-description">{stage.description}</p>

        {stage.total_challenges > 0 && (
          <>
            <ProgressBar
              value={stage.progress_pct}
              tone={stage.progress_pct === 100 ? "success" : "accent"}
            />
            <Link to="/challenges" className="node-link">
              View challenges →
            </Link>
          </>
        )}
        {wouldBeLocked && <p className="node-hint">Locked</p>}
      </Card>
    </li>
  );
}

function RoadmapSkeleton() {
  return (
    <div className="roadmap-page">
      <Card>
        <Skeleton height="1.75rem" width="280px" />
        <div style={{ height: "var(--space-4)" }} />
        <Skeleton height="400px" />
      </Card>
    </div>
  );
}
