/**
 * Submit results: score, per-test outcomes and the scoring breakdown.
 *
 * Hidden tests are listed (so learners can see how many exist and whether they
 * pass) but their failure messages are never shown — the backend already
 * withholds them, and this view must not imply otherwise.
 */

import type { SubmitResult } from "../api/client";
import type { TestResult } from "../api/client";
import { Badge, ProgressBar } from "./index";
import "./test-results.css";

export function TestResults({ result }: { result: SubmitResult }) {
  const visible = result.results.filter((test) => !test.hidden);
  const hidden = result.results.filter((test) => test.hidden);

  return (
    <div className="results">
      <div className="score-panel">
        <div className="score-dial" data-passed={result.score >= 60}>
          <span className="score-number">{result.score}</span>
          <span className="score-max">/100</span>
        </div>

        <div className="score-detail">
          <p className="score-summary">{result.summary}</p>
          <div className="score-stats">
            <span className="score-stat" data-tone="success">
              ✓ {result.passed} passed
            </span>
            {result.failed > 0 && (
              <span className="score-stat" data-tone="danger">
                ✗ {result.failed} failed
              </span>
            )}
            <span className="score-stat mono">{result.execution_time_ms} ms</span>
            <span className="score-stat mono">{result.memory_used_mb.toFixed(1)} MB</span>
          </div>

          {result.dimensions.length > 1 && (
            <div className="dimensions">
              {result.dimensions.map((dimension) => (
                <ProgressBar
                  key={dimension.name}
                  value={dimension.score}
                  label={`${dimension.name} · ${dimension.detail}`}
                  tone={dimension.score >= 80 ? "success" : "accent"}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="test-groups">
        {visible.length > 0 && (
          <TestGroup title="Visible tests" tests={visible} />
        )}
        {hidden.length > 0 && (
          <TestGroup
            title="Hidden tests"
            tests={hidden}
            note="Failure details are withheld so the graded suite stays unknown."
          />
        )}
      </div>
    </div>
  );
}

function TestGroup({ title, tests, note }: { title: string; tests: TestResult[]; note?: string }) {
  const passed = tests.filter((test) => test.status === "passed").length;

  return (
    <section className="test-group">
      <header className="test-group-head">
        <h3 className="test-group-title">{title}</h3>
        <Badge tone={passed === tests.length ? "success" : "warning"}>
          {passed}/{tests.length}
        </Badge>
      </header>
      {note !== undefined && <p className="test-group-note">{note}</p>}
      <ul className="test-list">
        {tests.map((test, index) => (
          <li key={`${test.name}-${index}`} className="test-item" data-status={test.status}>
            <span className="test-icon" aria-hidden="true">
              {iconFor(test.status)}
            </span>
            <div className="test-body">
              <code className="test-name">{test.name}</code>
              {test.message !== "" && <p className="test-message">{test.message}</p>}
            </div>
            <span className="test-duration mono muted">{test.duration_ms} ms</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function iconFor(status: string): string {
  switch (status) {
    case "passed":
      return "✓";
    case "failed":
      return "✗";
    case "skipped":
      return "○";
    default:
      return "!";
  }
}
