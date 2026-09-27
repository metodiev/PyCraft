/**
 * Challenge workspace — the heart of PyCraft.
 *
 * Three-pane layout: task briefing on the left, Monaco editor on the right, and
 * a results dock underneath. Run gives fast, ungraded feedback with raw output;
 * Submit grades against the hidden suite and reports the score breakdown.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import Editor from "@monaco-editor/react";
import "../lib/monaco-loader";
import { api, ApiError } from "../api/client";
import type { RunResult, SubmitResult } from "../api/client";
import { Badge, Button, DifficultyBadge, Notice, Skeleton } from "../components";
import { useApi } from "../hooks/useApi";
import { Markdown } from "../components/Markdown";
import { TestResults } from "../components/TestResults";
import { registerPyCraftTheme } from "../lib/monaco";
import "./workspace.css";

const STORAGE_PREFIX = "pycraft:draft:";

export function ChallengeWorkspace() {
  const { challengeId = "" } = useParams<{ challengeId: string }>();
  const challenge = useApi(() => api.getChallenge(challengeId), [challengeId]);

  const [source, setSource] = useState<string>("");
  const [runResult, setRunResult] = useState<RunResult | null>(null);
  const [submitResult, setSubmitResult] = useState<SubmitResult | null>(null);
  const [grading, setGrading] = useState<"run" | "submit" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const editorRef = useRef<unknown>(null);

  const entryFile = challenge.data?.entry_file ?? "solution.py";

  // Seed the editor from the starter, preferring an unsaved local draft so a
  // refresh never destroys work in progress.
  useEffect(() => {
    if (challenge.data === null) return;
    const draft = localStorage.getItem(`${STORAGE_PREFIX}${challengeId}`);
    setSource(draft ?? challenge.data.starter_code);
    setRunResult(null);
    setSubmitResult(null);
    setActionError(null);
  }, [challenge.data, challengeId]);

  // Persist drafts so an accidental refresh is recoverable.
  useEffect(() => {
    if (source === "") return;
    const timer = window.setTimeout(() => {
      localStorage.setItem(`${STORAGE_PREFIX}${challengeId}`, source);
    }, 400);
    return () => window.clearTimeout(timer);
  }, [source, challengeId]);

  const execute = useCallback(
    async (kind: "run" | "submit") => {
      setGrading(kind);
      setActionError(null);
      try {
        const files = { [entryFile]: source };
        if (kind === "run") {
          setRunResult(await api.run(challengeId, files));
        } else {
          setSubmitResult(await api.submit(challengeId, files));
        }
      } catch (cause) {
        setActionError(cause instanceof ApiError ? cause.message : "Execution failed");
      } finally {
        setGrading(null);
      }
    },
    [challengeId, entryFile, source],
  );

  const resetToStarter = useCallback(() => {
    if (challenge.data === null) return;
    setSource(challenge.data.starter_code);
    localStorage.removeItem(`${STORAGE_PREFIX}${challengeId}`);
    setRunResult(null);
    setSubmitResult(null);
  }, [challenge.data, challengeId]);

  // Ctrl/Cmd+Enter runs, matching common coding platforms.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
        event.preventDefault();
        if (grading === null) void execute("run");
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [execute, grading]);

  const visibleTests = useMemo(() => Object.keys(challenge.data?.visible_tests ?? {}), [challenge.data]);

  if (challenge.loading) return <WorkspaceSkeleton />;
  if (challenge.error !== null) {
    return (
      <div className="workspace-error">
        <Notice tone="danger">{challenge.error}</Notice>
        <Link to="/challenges" className="link-button">
          ← Back to challenges
        </Link>
      </div>
    );
  }
  if (challenge.data === null) return null;

  return (
    <div className="workspace">
      <header className="workspace-bar">
        <div className="workspace-bar-left">
          <Link to="/challenges" className="back-link" aria-label="Back to challenges">
            ←
          </Link>
          <h1 className="workspace-title">{challenge.data.title}</h1>
          <DifficultyBadge difficulty={challenge.data.difficulty} />
          <Badge>{challenge.data.points} XP</Badge>
        </div>
        <div className="workspace-bar-right">
          <span className="runtime-chip" title="Execution sandbox">
            Python {challenge.data.python_version}
          </span>
          <span className="runtime-chip" title="Per-submission resource limits">
            {challenge.data.time_limit_ms / 1000}s · {challenge.data.memory_limit_mb}MB
          </span>
        </div>
      </header>

      <div className="workspace-body">
        <section className="briefing" aria-label="Challenge briefing">
          <Markdown source={challenge.data.description} />

          <details className="visible-tests">
            <summary>
              Visible tests <span className="count">{visibleTests.length}</span>
            </summary>
            {visibleTests.map((name) => (
              <pre key={name} className="test-source">
                <code>{challenge.data?.visible_tests[name]}</code>
              </pre>
            ))}
          </details>
        </section>

        <section className="editor-pane" aria-label="Code editor">
          <div className="editor-toolbar">
            <span className="file-chip">{entryFile}</span>
            <div className="toolbar-actions">
              <Button variant="ghost" onClick={resetToStarter} title="Restore the starter code">
                Reset
              </Button>
              <Button
                variant="secondary"
                onClick={() => void execute("run")}
                busy={grading === "run"}
                disabled={grading !== null}
                title="Run (Ctrl+Enter)"
              >
                ▶ Run
              </Button>
              <Button
                variant="primary"
                onClick={() => void execute("submit")}
                busy={grading === "submit"}
                disabled={grading !== null}
                title="Grade against all tests"
              >
                Submit
              </Button>
            </div>
          </div>

          <div className="editor-host">
            <Editor
              height="100%"
              language="python"
              theme="pycraft-dark"
              value={source}
              beforeMount={registerPyCraftTheme}
              onMount={(editor) => {
                editorRef.current = editor;
              }}
              onChange={(value) => setSource(value ?? "")}
              options={{
                fontSize: 14,
                fontFamily: "'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace",
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
                renderLineHighlight: "line",
                tabSize: 4,
                insertSpaces: true,
                automaticLayout: true,
                padding: { top: 16, bottom: 16 },
                smoothScrolling: true,
                cursorBlinking: "smooth",
                bracketPairColorization: { enabled: true },
                suggestSelection: "first",
                quickSuggestions: { other: true, comments: false, strings: false },
                formatOnPaste: true,
                wordWrap: "off",
              }}
            />
          </div>
        </section>
      </div>

      <section className="results-dock" aria-label="Results" aria-live="polite">
        {actionError !== null && <Notice tone="danger">{actionError}</Notice>}
        <ResultsPanel runResult={runResult} submitResult={submitResult} grading={grading} />
      </section>
    </div>
  );
}

function ResultsPanel({
  runResult,
  submitResult,
  grading,
}: {
  runResult: RunResult | null;
  submitResult: SubmitResult | null;
  grading: "run" | "submit" | null;
}) {
  if (grading !== null) {
    return <p className="dock-idle">Executing in the sandbox…</p>;
  }

  if (submitResult !== null) {
    return <TestResults result={submitResult} />;
  }

  if (runResult !== null) {
    return (
      <div className="run-output">
        <div className="run-meta">
          <Badge tone={runResult.status === "completed" ? "success" : "warning"}>{runResult.status}</Badge>
          <span className="mono muted">{runResult.execution_time_ms} ms</span>
          <span className="mono muted">{runResult.memory_used_mb.toFixed(1)} MB</span>
          {runResult.exit_code !== null && <span className="mono muted">exit {runResult.exit_code}</span>}
        </div>
        {runResult.stdout !== "" && (
          <pre className="output-block" data-stream="stdout">
            {runResult.stdout}
          </pre>
        )}
        {runResult.stderr !== "" && (
          <pre className="output-block" data-stream="stderr">
            {runResult.stderr}
          </pre>
        )}
        {runResult.stdout === "" && runResult.stderr === "" && (
          <p className="dock-idle">No output produced.</p>
        )}
      </div>
    );
  }

  return (
    <p className="dock-idle">
      Press <kbd>Run</kbd> for quick feedback against the visible tests, or <kbd>Submit</kbd> to grade
      against the full suite.
    </p>
  );
}

function WorkspaceSkeleton() {
  return (
    <div className="workspace">
      <div className="workspace-bar">
        <Skeleton height="1.5rem" width="320px" />
      </div>
      <div className="workspace-body">
        <div className="briefing">
          <Skeleton height="80%" />
        </div>
        <div className="editor-pane">
          <Skeleton height="100%" />
        </div>
      </div>
    </div>
  );
}
