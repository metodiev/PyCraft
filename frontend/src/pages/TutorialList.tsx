/**
 * Tutorials — reading material grouped by engineering track.
 *
 * Tutorials sit beside the challenges rather than inside them: a learner reads
 * to understand a concept, then practises it. Nothing here is graded, so the
 * only state shown is what the reader has already covered.
 */

import { Link, useSearchParams } from "react-router-dom";
import { useMemo } from "react";
import { api } from "../api/client";
import type { TutorialSummary, TutorialTrack } from "../api/client";
import { Badge, Card, EmptyState, Notice, Skeleton } from "../components";
import { useApi } from "../hooks/useApi";
import "./tutorials.css";

export function TutorialList() {
  const { data, error, loading, reload } = useApi(() => api.listTutorials(), []);
  const [params, setParams] = useSearchParams();

  const activeTrack = params.get("track");
  const tracks = useMemo(() => data?.tracks ?? [], [data]);
  const visible = useMemo(
    () => (activeTrack === null ? tracks : tracks.filter((t) => t.track === activeTrack)),
    [tracks, activeTrack],
  );

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
  if (data === null) return null;
  if (data.total === 0) {
    return (
      <EmptyState
        title="No tutorials available"
        hint="Add content under tutorials/ and restart the API."
      />
    );
  }

  return (
    <div className="tutorial-list">
      <header className="list-head">
        <h1>Tutorials</h1>
        <p className="list-sub">
          {data.total} articles · about {formatMinutes(data.reading_minutes)} of reading ·{" "}
          {data.read_count} read
        </p>
        <p className="tutorial-note">
          Tutorials explain the technology behind a challenge. Completion is still earned by
          passing tests — reading is never graded.
        </p>
      </header>

      <TrackFilter tracks={tracks} active={activeTrack} onSelect={setParams} />

      {visible.map((track) => (
        <TrackSection key={track.track} track={track} />
      ))}
    </div>
  );
}

/** Track chips double as the page's filter, and stay out of the way when there is nothing to filter. */
function TrackFilter({
  tracks,
  active,
  onSelect,
}: {
  tracks: TutorialTrack[];
  active: string | null;
  onSelect: (params: URLSearchParams) => void;
}) {
  if (tracks.length < 2) return null;

  const choose = (track: string | null) => {
    const next = new URLSearchParams();
    if (track !== null) next.set("track", track);
    onSelect(next);
  };

  return (
    <nav className="track-filter" aria-label="Filter by track">
      <button
        type="button"
        className="track-chip"
        aria-pressed={active === null}
        onClick={() => choose(null)}
      >
        All tracks
      </button>
      {tracks.map((track) => (
        <button
          key={track.track}
          type="button"
          className="track-chip"
          aria-pressed={active === track.track}
          onClick={() => choose(track.track)}
        >
          {track.label}
          <span className="chip-count">{track.total}</span>
        </button>
      ))}
    </nav>
  );
}

function TrackSection({ track }: { track: TutorialTrack }) {
  return (
    <Card className="track-card">
      <header className="track-head">
        <h2 className="track-title">{track.label}</h2>
        <Badge tone={track.read_count === track.total ? "success" : "neutral"}>
          {track.read_count}/{track.total} read
        </Badge>
      </header>
      <div className="tutorial-grid">
        {track.tutorials.map((tutorial) => (
          <TutorialCard key={tutorial.id} tutorial={tutorial} />
        ))}
      </div>
    </Card>
  );
}

function TutorialCard({ tutorial }: { tutorial: TutorialSummary }) {
  return (
    <Link to={`/tutorials/${tutorial.id}`} className="tutorial-card" data-read={tutorial.read}>
      <div className="tutorial-card-head">
        <span className="reading-time">{tutorial.reading_minutes} min read</span>
        {tutorial.read && (
          <span className="read-mark" title="Read">
            ✓
          </span>
        )}
      </div>

      <h3 className="tutorial-card-title">{tutorial.title}</h3>
      <p className="tutorial-card-summary">{tutorial.summary}</p>

      <footer className="tutorial-card-foot">
        <span className="tutorial-tags">
          {tutorial.tags.slice(0, 3).map((tag) => (
            <span key={tag} className="tutorial-tag">
              {tag}
            </span>
          ))}
        </span>
      </footer>
    </Link>
  );
}

function formatMinutes(total: number): string {
  if (total < 60) return `${total} min`;
  const hours = Math.floor(total / 60);
  const minutes = total % 60;
  return minutes === 0 ? `${hours} h` : `${hours} h ${minutes} min`;
}

function ListSkeleton() {
  return (
    <div className="tutorial-list">
      <Card>
        <Skeleton height="1.5rem" width="200px" />
        <div style={{ height: "var(--space-4)" }} />
        <Skeleton height="180px" />
      </Card>
    </div>
  );
}
