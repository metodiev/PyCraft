/**
 * Dashboard — the learner's engineering journey at a glance.
 *
 * Mirrors the layout the product spec calls for: level position, skill
 * breakdown, recommended and in-progress work, and recent submissions.
 */

import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { ChallengeSummary, Dashboard as DashboardData, RecentSubmission } from "../api/client";
import { Badge, Button, Card, CardHeader, DifficultyBadge, EmptyState, Notice, ProgressBar, Skeleton } from "../components";
import { useApi } from "../hooks/useApi";
import { LEVEL_ORDER } from "../lib/levels";
import "./dashboard.css";

export function Dashboard() {
  const { data, error, loading, reload } = useApi(() => api.getDashboard(), []);

  if (loading) return <DashboardSkeleton />;
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

  return (
    <div className="dashboard">
      <JourneyHeader progress={data.progress} />

      <div className="dashboard-grid">
        <SkillsCard data={data} />
        <NextUpCard data={data} />
      </div>

      <RoadmapStrip data={data} />
      <RecentCard submissions={data.recent_submissions} />
    </div>
  );
}

/** Level rail: where the learner sits between Junior and Principal. */
function JourneyHeader({ progress }: { progress: DashboardData["progress"] }) {
  const index = LEVEL_ORDER.findIndex((level) => level.id === progress.level_id);
  const position = index === -1 ? 0 : index;

  return (
    <Card className="journey-card">
      <div className="journey-head">
        <div>
          <p className="journey-eyebrow">Your engineering journey</p>
          <h1 className="journey-title">{progress.level_label}</h1>
        </div>
        <div className="journey-stats">
          <Stat label="XP" value={progress.xp.toLocaleString()} />
          <Stat label="Completed" value={`${progress.completed_challenges} / ${progress.total_challenges}`} />
          <Stat label="Progress" value={`${progress.completion_pct}%`} />
        </div>
      </div>

      <div className="level-rail" role="img" aria-label={`Level ${progress.level_label}`}>
        <div className="level-track" />
        <div
          className="level-fill"
          style={{ width: `${(position / (LEVEL_ORDER.length - 1)) * 100}%` }}
        />
        {LEVEL_ORDER.map((level, i) => (
          <div
            key={level.id}
            className="level-node"
            data-state={i < position ? "done" : i === position ? "current" : "todo"}
            style={{ left: `${(i / (LEVEL_ORDER.length - 1)) * 100}%` }}
          >
            <span className="level-dot" />
            <span className="level-name">{level.label}</span>
          </div>
        ))}
      </div>

      {progress.next_level_label !== null && progress.next_level_xp !== null && (
        <p className="journey-next">
          {progress.next_level_xp - progress.xp} XP to{" "}
          <strong>{progress.next_level_label}</strong>
        </p>
      )}
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat">
      <span className="stat-value">{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  );
}

function SkillsCard({ data }: { data: DashboardData }) {
  return (
    <Card>
      <CardHeader title="Skill breakdown" />
      {data.skills.length === 0 ? (
        <EmptyState title="No skills tracked yet" hint="Solve a challenge to start building your graph." />
      ) : (
        <div className="skill-list">
          {data.skills.slice(0, 7).map((skill) => (
            <div key={skill.skill} className="skill-row">
              <ProgressBar
                value={skill.mastery}
                label={`${skill.label} · ${skill.challenges_completed}/${skill.challenges_total}`}
                tone={skill.mastery >= 80 ? "success" : "accent"}
              />
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function NextUpCard({ data }: { data: DashboardData }) {
  const continueChallenge = data.continue_challenge;
  const recommended = data.recommended_challenge;

  return (
    <Card>
      <CardHeader title={continueChallenge !== null ? "Continue learning" : "Recommended next"} />
      {continueChallenge === null && recommended === null ? (
        <EmptyState title="All caught up" hint="Every available challenge is complete. New content is on the way." />
      ) : (
        <div className="next-list">
          {continueChallenge !== null && <ChallengeTeaser challenge={continueChallenge} cta="Resume" />}
          {recommended !== null && recommended.id !== continueChallenge?.id && (
            <ChallengeTeaser challenge={recommended} cta="Start" />
          )}
        </div>
      )}
    </Card>
  );
}

function ChallengeTeaser({ challenge, cta }: { challenge: ChallengeSummary; cta: string }) {
  return (
    <article className="teaser">
      <div className="teaser-top">
        <DifficultyBadge difficulty={challenge.difficulty} />
        <Badge>{challenge.points} XP</Badge>
      </div>
      <h3 className="teaser-title">{challenge.title}</h3>
      <p className="teaser-summary">{challenge.summary}</p>
      <Link to={`/challenges/${challenge.id}`} className="teaser-link">
        <Button variant="primary">{cta}</Button>
      </Link>
    </article>
  );
}

/** Compact roadmap overview: every stage with its completion state. */
function RoadmapStrip({ data }: { data: DashboardData }) {
  const active = data.roadmap.filter((stage) => stage.total_challenges > 0);

  return (
    <Card>
      <CardHeader
        title="Learning roadmap"
        action={
          <Link to="/roadmap" className="link-button">
            View full roadmap
          </Link>
        }
      />
      {active.length === 0 ? (
        <EmptyState title="Roadmap is empty" />
      ) : (
        <ol className="roadmap-strip">
          {data.roadmap.map((stage) => (
            <li key={stage.id} className="strip-item" data-empty={stage.total_challenges === 0}>
              <div className="strip-marker" data-complete={stage.progress_pct === 100} />
              <div className="strip-body">
                <span className="strip-title">{stage.title}</span>
                <span className="strip-meta">
                  {stage.total_challenges === 0
                    ? "Coming soon"
                    : `${stage.completed_challenges}/${stage.total_challenges} complete`}
                </span>
              </div>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}

function RecentCard({ submissions }: { submissions: RecentSubmission[] }) {
  return (
    <Card>
      <CardHeader title="Recent submissions" />
      {submissions.length === 0 ? (
        <EmptyState title="No submissions yet" hint="Run some code to see your history here." />
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Challenge</th>
                <th scope="col">Type</th>
                <th scope="col">Result</th>
                <th scope="col">Score</th>
                <th scope="col">Time</th>
              </tr>
            </thead>
            <tbody>
              {submissions.map((submission) => (
                <tr key={submission.id}>
                  <td>
                    <Link to={`/challenges/${submission.challenge_id}`} className="table-link">
                      {submission.challenge_title}
                    </Link>
                  </td>
                  <td>
                    <Badge tone={submission.kind === "submit" ? "accent" : "neutral"}>
                      {submission.kind}
                    </Badge>
                  </td>
                  <td className="mono">
                    {submission.passed}/{submission.total_tests}
                  </td>
                  <td className="mono">{submission.score ?? "—"}</td>
                  <td className="mono muted">{submission.execution_time_ms ?? "—"} ms</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

function DashboardSkeleton() {
  return (
    <div className="dashboard">
      <Card className="journey-card">
        <Skeleton height="1.75rem" width="240px" />
        <div style={{ height: "var(--space-5)" }} />
        <Skeleton height="6px" />
      </Card>
      <div className="dashboard-grid">
        <Card>
          <Skeleton height="1.25rem" width="160px" />
          <div style={{ height: "var(--space-4)" }} />
          <Skeleton height="120px" />
        </Card>
        <Card>
          <Skeleton height="1.25rem" width="160px" />
          <div style={{ height: "var(--space-4)" }} />
          <Skeleton height="120px" />
        </Card>
      </div>
    </div>
  );
}
