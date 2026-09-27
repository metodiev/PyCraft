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
import type { ChallengeDetail, RunResult, SubmitResult } from "../api/client";
import { Badge, Button, DifficultyBadge, Notice, Skeleton } from "../components";
import { useApi } from "../hooks/useApi";
import { Markdown } from "../components/Markdown";
import { TestResults } from "../components/TestResults";
import { registerPyCraftTheme } from "../lib/monaco";
import "./workspace.css";

const STORAGE_PREFIX = "pycraft:draft:";

/** The files a learner may edit, in a stable order with the entry file first. */
function editableFiles(challenge: ChallengeDetail): string[] {
  const declared = Object.keys(challenge.starter_files ?? {});
  const names = declared.length > 0 ? declared : [challenge.entry_file];
  return names.sort((left, right) => {
    if (left === challenge.entry_file) return -1;
    if (right === challenge.entry_file) return 1;
    return left.localeCompare(right);
  });
}

function draftKey(challengeId: string, fileName: string): string {
  return `${STORAGE_PREFIX}${challengeId}:${fileName}`;
}

/** Read any saved drafts for this challenge, keyed by filename. */
function readDrafts(challengeId: string, files: string[]): Record<string, string> {
  const drafts: Record<string, string> = {};
  for (const name of files) {
    const stored = localStorage.getItem(draftKey(challengeId, name));
    if (stored !== null) drafts[name] = stored;
  }
  return drafts;
}

export function ChallengeWorkspace() {
  const { challengeId = "" } = useParams<{ challengeId: string }>();
  const challenge = useApi(() => api.getChallenge(challengeId), [challengeId]);

  // One buffer per editable file. A single-file challenge has exactly one, so
  // the editor looks unchanged; a project gets a file switcher.
  const [buffers, setBuffers] = useState<Record<string, string>>({});
  const [activeFile, setActiveFile] = useState<string>("");
  const [runResult, setRunResult] = useState<RunResult | null>(null);
  const [submitResult, setSubmitResult] = useState<SubmitResult | null>(null);
  const [grading, setGrading] = useState<"run" | "submit" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const editorRef = useRef<unknown>(null);

  const entryFile = challenge.data?.entry_file ?? "solution.py";
  const fileNames = useMemo(
    () => (challenge.data === null ? [] : editableFiles(challenge.data)),
    [challenge.data],
  );
  const isProject = challenge.data?.is_project === true && fileNames.length > 1;

  // Seed every buffer from the starter, preferring unsaved local drafts so a
  // refresh never destroys work in progress.
  useEffect(() => {
    if (challenge.data === null) return;
    const names = editableFiles(challenge.data);
    const drafts = readDrafts(challengeId, names);
    const seeded: Record<string, string> = {};
    for (const name of names) {
      const starter = challenge.data.starter_files?.[name] ?? challenge.data.starter_code;
      seeded[name] = drafts[name] ?? starter;
    }
    const initial =
      names.find((name) => name === challenge.data?.entry_file) ?? names[0] ?? challenge.data.entry_file;
    setBuffers(seeded);
    setActiveFile(initial);
    setRunResult(null);
    setSubmitResult(null);
    setActionError(null);
  }, [challenge.data, challengeId]);

  // Persist drafts so an accidental refresh is recoverable.
  useEffect(() => {
    const active = buffers[activeFile];
    if (active === undefined) return;
    const timer = window.setTimeout(() => {
      localStorage.setItem(draftKey(challengeId, activeFile), active);
    }, 400);
    return () => window.clearTimeout(timer);
  }, [buffers, activeFile, challengeId]);

  const source = buffers[activeFile] ?? "";

  const setSource = useCallback(
    (value: string) => setBuffers((current) => ({ ...current, [activeFile]: value })),
    [activeFile],
  );

  const execute = useCallback(
    async (kind: "run" | "submit") => {
      setGrading(kind);
      setActionError(null);
      try {
        // Every editable file is submitted: a project's modules must travel
        // together, and an untouched helper has to keep resolving.
        const files = { ...buffers };
        if (Object.keys(files).length === 0) files[entryFile] = "";
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
    [challengeId, entryFile, buffers],
  );

  const resetToStarter = useCallback(() => {
    if (challenge.data === null) return;
    const seeded: Record<string, string> = {};
    for (const name of editableFiles(challenge.data)) {
      seeded[name] = challenge.data.starter_files?.[name] ?? challenge.data.starter_code;
      localStorage.removeItem(draftKey(challengeId, name));
    }
    setBuffers(seeded);
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

          {challenge.data.rubric.length > 0 && (
            <details className="visible-tests" open>
              <summary>
                How this is scored <span className="count">{challenge.data.rubric.length}</span>
              </summary>
              <ul className="rubric-list">
                {challenge.data.rubric.map((entry) => (
                  <li key={entry.label}>
                    <span className="rubric-label">{entry.label}</span>
                    <span className="rubric-weight">{entry.weight}%</span>
                    <p className="rubric-detail">{entry.description}</p>
                  </li>
                ))}
              </ul>
            </details>
          )}

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
            {isProject ? (
              <div className="file-tabs" role="tablist" aria-label="Project files">
                {fileNames.map((name) => (
                  <button
                    key={name}
                    type="button"
                    role="tab"
                    aria-selected={name === activeFile}
                    className={`file-tab${name === activeFile ? " is-active" : ""}`}
                    onClick={() => setActiveFile(name)}
                    title={name === entryFile ? `${name} (entry file)` : name}
                  >
                    {name}
                    {name === entryFile && <span className="entry-dot" aria-label="entry file" />}
                  </button>
                ))}
              </div>
            ) : (
              <span className="file-chip">{activeFile || entryFile}</span>
            )}
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
