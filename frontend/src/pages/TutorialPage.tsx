/**
 * One tutorial: the article, plus navigation to the next and previous piece.
 *
 * The read marker is deliberate rather than automatic — scrolling to the
 * bottom is not the same as reading, and claiming otherwise would be false
 * precision. It grants nothing, so the worst case of a careless click is a
 * tick that the reader can clear again.
 */

import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { TutorialCatalogue, TutorialDetail } from "../api/client";
import { Badge, Button, Card, Notice, Skeleton } from "../components";
import { Markdown } from "../components/Markdown";
import { useApi } from "../hooks/useApi";
import "./tutorials.css";

export function TutorialPage() {
  const { tutorialId = "" } = useParams();
  const { data, error, loading, reload } = useApi(() => api.getTutorial(tutorialId), [tutorialId]);
  // The catalogue is already cached by the browser after the list page; this
  // call exists only to find the neighbouring articles by position.
  const catalogue = useApi(() => api.listTutorials(), []);

  if (loading) return <ArticleSkeleton />;
  if (error !== null) {
    return (
      <>
        <Notice tone="danger">
          {error}{" "}
          <button className="link-button" onClick={reload}>
            Retry
          </button>
        </Notice>
        <p className="tutorial-back">
          <Link to="/tutorials">← All tutorials</Link>
        </p>
      </>
    );
  }
  if (data === null) return null;

  return (
    <div className="tutorial-page">
      {/* Keyed by id so navigating to a sibling article resets the read marker
          and any error, rather than needing an effect to resync them. */}
      <Article key={data.id} tutorial={data} catalogue={catalogue.data} reload={reload} />
    </div>
  );
}

function Article({
  tutorial,
  catalogue,
  reload,
}: {
  tutorial: TutorialDetail;
  catalogue: TutorialCatalogue | null;
  reload: () => void;
}) {
  const [read, setRead] = useState(tutorial.read);
  const [busy, setBusy] = useState(false);
  const [markError, setMarkError] = useState<string | null>(null);

  const neighbours = useMemo(
    () => findNeighbours(catalogue, tutorial.id),
    [catalogue, tutorial.id],
  );

  const toggleRead = async () => {
    setBusy(true);
    setMarkError(null);
    try {
      const result = read
        ? await api.clearTutorialRead(tutorial.id)
        : await api.markTutorialRead(tutorial.id);
      setRead(result.read);
      reload();
    } catch {
      setMarkError("Could not update your reading progress. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <article className="tutorial-article">
      <nav className="tutorial-back" aria-label="Breadcrumb">
        <Link to="/tutorials">← All tutorials</Link>
        <Link to={`/tutorials?track=${encodeURIComponent(tutorial.track)}`} className="crumb-track">
          {tutorial.track.replace(/-/g, " ")}
        </Link>
      </nav>

      <header className="article-head">
        <div className="article-meta">
          <span className="reading-time">{tutorial.reading_minutes} min read</span>
          <span className="meta-sep" aria-hidden="true">
            ·
          </span>
          <span className="article-words">{tutorial.word_count.toLocaleString()} words</span>
          {read && <Badge tone="success">Read</Badge>}
        </div>
        <h1>{tutorial.title}</h1>
        {tutorial.summary !== "" && <p className="article-summary">{tutorial.summary}</p>}

        <div className="article-actions">
          <Button variant={read ? "secondary" : "primary"} onClick={toggleRead} busy={busy}>
            {read ? "Mark as unread" : "Mark as read"}
          </Button>
        </div>
        {markError !== null && <Notice tone="danger">{markError}</Notice>}
      </header>

      <Card className="article-body">
        <Markdown source={tutorial.content} />
      </Card>

      {tutorial.related_challenge !== null && (
        <Card className="article-practice">
          <div>
            <h2 className="practice-title">Practise this</h2>
            <p className="practice-hint">
              Reading is not graded. Apply it in the challenge and let the tests decide.
            </p>
          </div>
          <Link to={`/challenges/${tutorial.related_challenge}`} className="btn btn-primary">
            Open challenge →
          </Link>
        </Card>
      )}

      {(neighbours.previous !== null || neighbours.next !== null) && (
        <nav className="article-nav" aria-label="Tutorial navigation">
          {neighbours.previous !== null ? (
            <Link to={`/tutorials/${neighbours.previous.id}`} className="article-nav-link">
              <span className="nav-direction">← Previous</span>
              <span className="nav-title">{neighbours.previous.title}</span>
            </Link>
          ) : (
            <span />
          )}
          {neighbours.next !== null && (
            <Link to={`/tutorials/${neighbours.next.id}`} className="article-nav-link next">
              <span className="nav-direction">Next →</span>
              <span className="nav-title">{neighbours.next.title}</span>
            </Link>
          )}
        </nav>
      )}
    </article>
  );
}

/** Neighbours in the tutorial's own track, by declared order. */
function findNeighbours(catalogue: TutorialCatalogue | null, id: string) {
  if (catalogue === null) return { previous: null, next: null };

  for (const track of catalogue.tracks) {
    const index = track.tutorials.findIndex((entry) => entry.id === id);
    if (index === -1) continue;
    return {
      previous: index > 0 ? track.tutorials[index - 1] ?? null : null,
      next: index < track.tutorials.length - 1 ? track.tutorials[index + 1] ?? null : null,
    };
  }
  return { previous: null, next: null };
}

function ArticleSkeleton() {
  return (
    <div className="tutorial-page">
      <Card>
        <Skeleton height="1.25rem" width="180px" />
        <div style={{ height: "var(--space-4)" }} />
        <Skeleton height="2rem" width="70%" />
        <div style={{ height: "var(--space-5)" }} />
        <Skeleton height="320px" />
      </Card>
    </div>
  );
}
