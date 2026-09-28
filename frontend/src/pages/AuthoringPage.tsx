/**
 * Challenge authoring studio.
 *
 * Authors write a challenge as a form, validate it against the server, and
 * publish it into the content directory. Two ideas shape the screen:
 *
 * 1. **Validate before publishing.** The server returns *every* problem at
 *    once, so the editor groups them by field instead of making the author fix
 *    them one at a time.
 * 2. **Nothing is lost.** The draft persists to `localStorage` on every change,
 *    so a refresh, a crash or a failed publish never costs work.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import Editor from "@monaco-editor/react";
import "../lib/monaco-loader";
import { api, ApiError } from "../api/client";
import type {
  AuthoringCatalogue,
  AuthoringCatalogueEntry,
  DraftPayload,
  TrackOption,
  ValidationIssue,
  ValidationResult,
} from "../api/client";
import { Badge, Button, Card, CardHeader, Notice, Skeleton } from "../components";
import { useApi } from "../hooks/useApi";
import { registerPyCraftTheme } from "../lib/monaco";
import { monacoThemeName, useResolvedTheme } from "../lib/theme";
import "./authoring.css";

const DRAFT_KEY = "pycraft:authoring:draft";
const EMPTY_DRAFT: DraftPayload = {
  slug: "",
  track: "",
  title: "",
  summary: "",
  difficulty: "beginner",
  level: "junior",
  module: "General",
  points: 50,
  order_index: 1,
  time_limit_ms: 5000,
  memory_limit_mb: 128,
  python_version: "3.12",
  skills: [],
  tags: [],
  description: "",
  starter_code: '"""Starter.\n\nReplace this with the skeleton a learner begins from.\n"""\n\n\n# TODO: implement.\nraise NotImplementedError\n',
  visible_tests: { "test_visible.py": "" },
  hidden_tests: { "test_hidden.py": "" },
};

const DIFFICULTIES = ["beginner", "easy", "intermediate", "advanced", "expert"];
const LEVELS = ["junior", "intermediate", "senior", "staff", "principal"];

/** Which editor tab is open below the form. */
type Tab = "description" | "starter" | "visible" | "hidden";

function readLocalDraft(): DraftPayload | null {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    if (raw === null) return null;
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return null;
    // Merge over the defaults so a draft written by an older build cannot leave
    // the form with missing fields.
    return { ...EMPTY_DRAFT, ...(parsed as Partial<DraftPayload>) };
  } catch {
    return null;
  }
}

export function AuthoringPage() {
  const { track: routeTrack = "", slug: routeSlug = "" } = useParams<{
    track: string;
    slug: string;
  }>();
  const access = useApi(() => api.getAuthoringAccess(), []);
  const tracks = useApi(() => api.listAuthorTracks(), []);
  const catalogue = useApi(() => api.getAuthoringCatalogue(), []);

  const [draft, setDraft] = useState<DraftPayload>(() => readLocalDraft() ?? EMPTY_DRAFT);
  const [tab, setTab] = useState<Tab>("description");
  const [result, setResult] = useState<ValidationResult | null>(null);
  const [busy, setBusy] = useState<"validate" | "publish" | null>(null);
  const [fatal, setFatal] = useState<string | null>(null);
  const [published, setPublished] = useState<string | null>(null);
  const [loadingExisting, setLoadingExisting] = useState(routeSlug !== "");
  const loadedKey = useRef<string | null>(null);

  // Load an existing challenge when the route names one, once per id.
  useEffect(() => {
    if (routeSlug === "" || routeTrack === "") return;
    const key = `${routeTrack}/${routeSlug}`;
    if (loadedKey.current === key) return;
    loadedKey.current = key;

    setLoadingExisting(true);
    api
      .getDraft(routeTrack, routeSlug)
      .then((existing) => {
        setDraft(existing);
        setResult(null);
      })
      .catch((cause: unknown) => {
        setFatal(cause instanceof ApiError ? cause.message : "Could not load the challenge");
      })
      .finally(() => setLoadingExisting(false));
  }, [routeTrack, routeSlug]);

  // Persist on every change; a failed write (private mode) must not break editing.
  useEffect(() => {
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
    } catch {
      // Ignore: the session stays usable without draft persistence.
    }
  }, [draft]);

  const update = useCallback(<K extends keyof DraftPayload>(key: K, value: DraftPayload[K]) => {
    setDraft((current) => ({ ...current, [key]: value }));
  }, []);

  const updateTest = useCallback((bucket: "visible_tests" | "hidden_tests", name: string, source: string) => {
    setDraft((current) => ({
      ...current,
      [bucket]: { ...current[bucket], [name]: source },
    }));
  }, []);

  const renameTest = useCallback((bucket: "visible_tests" | "hidden_tests", from: string, to: string) => {
    setDraft((current) => {
      const entries = Object.entries(current[bucket]);
      const next: Record<string, string> = {};
      for (const [name, source] of entries) {
        next[name === from ? to : name] = source;
      }
      return { ...current, [bucket]: next };
    });
  }, []);

  const addTest = useCallback((bucket: "visible_tests" | "hidden_tests") => {
    setDraft((current) => {
      let index = Object.keys(current[bucket]).length + 1;
      let name = bucket === "visible_tests" ? `test_${index}.py` : `test_hidden_${index}.py`;
      while (name in current[bucket]) {
        index += 1;
        name = bucket === "visible_tests" ? `test_${index}.py` : `test_hidden_${index}.py`;
      }
      return { ...current, [bucket]: { ...current[bucket], [name]: "" } };
    });
  }, []);

  const removeTest = useCallback((bucket: "visible_tests" | "hidden_tests", name: string) => {
    setDraft((current) => {
      const next = { ...current[bucket] };
      delete next[name];
      return { ...current, [bucket]: next };
    });
  }, []);

  const run = useCallback(
    async (mode: "validate" | "publish") => {
      setBusy(mode);
      setFatal(null);
      setPublished(null);
      try {
        const outcome =
          mode === "validate" ? await api.validateDraft(draft) : await api.publishDraft(draft);
        setResult(outcome);
        if (mode === "publish" && outcome.valid) {
          setPublished(`${draft.track}/${draft.slug}`);
          catalogue.reload();
        }
      } catch (cause) {
        setFatal(cause instanceof ApiError ? cause.message : "The request failed");
      } finally {
        setBusy(null);
      }
    },
    [draft, catalogue],
  );

  const resetDraft = useCallback(() => {
    setDraft(EMPTY_DRAFT);
    setResult(null);
    setPublished(null);
    setFatal(null);
    try {
      localStorage.removeItem(DRAFT_KEY);
    } catch {
      // Ignore.
    }
  }, []);

  // Issues grouped by field, so the form can annotate the exact input.
  const issuesByField = useMemo(() => {
    const grouped = new Map<string, ValidationIssue[]>();
    for (const issue of result?.issues ?? []) {
      const list = grouped.get(issue.field) ?? [];
      list.push(issue);
      grouped.set(issue.field, list);
    }
    return grouped;
  }, [result]);

  if (access.loading) return <AuthoringSkeleton />;

  if (access.data !== null && !access.data.can_author) {
    return (
      <div className="authoring-denied">
        <Notice tone="warning">
          Authoring requires the <strong>author</strong> or <strong>admin</strong> role. Your role is{" "}
          <code>{access.data.role}</code>.
        </Notice>
        <Link to="/challenges" className="link-button">
          ← Back to challenges
        </Link>
      </div>
    );
  }

  if (loadingExisting) return <AuthoringSkeleton />;

  const trackOptions: TrackOption[] = tracks.data ?? [];
  const isEdit = routeSlug !== "";

  return (
    <div className="authoring">
      <header className="authoring-bar">
        <div className="authoring-bar-left">
          <Link to="/authoring" className="back-link" aria-label="Back to the catalogue">
            ←
          </Link>
          <h1 className="authoring-title">{isEdit ? `Edit: ${draft.title || routeSlug}` : "New challenge"}</h1>
          {draft.track !== "" && <Badge>{draft.track}</Badge>}
        </div>
        <div className="authoring-bar-right">
          <Button variant="ghost" onClick={resetDraft} title="Clear the draft and start over">
            New draft
          </Button>
          <Button
            variant="secondary"
            onClick={() => void run("validate")}
            busy={busy === "validate"}
            disabled={busy !== null}
          >
            Validate
          </Button>
          <Button
            variant="primary"
            onClick={() => void run("publish")}
            busy={busy === "publish"}
            disabled={busy !== null}
            title="Validate and write the challenge to disk"
          >
            Publish
          </Button>
        </div>
      </header>

      <div className="authoring-body">
        <div className="authoring-form">
          {fatal !== null && <Notice tone="danger">{fatal}</Notice>}
          {published !== null && (
            <Notice tone="success">
              Published <code>{published}</code>. It is live now —{" "}
              <Link to={`/challenges/${published.replace("/", "-")}`}>open it</Link>.
            </Notice>
          )}
          {result !== null && <ValidationPanel result={result} />}

          <Card>
            <CardHeader title="Identity" />
            <div className="field-grid">
              <Field label="Track" issues={issuesByField.get("track")} hint="Which roadmap stage this belongs to.">
                <select
                  className="field-input"
                  value={draft.track}
                  onChange={(event) => update("track", event.target.value)}
                >
                  <option value="">Select a track…</option>
                  {trackOptions.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </Field>

              <Field label="Slug" issues={issuesByField.get("slug")} hint="Becomes part of the id: <track>-<slug>.">
                <input
                  className="field-input"
                  value={draft.slug}
                  placeholder="async-worker-pool"
                  onChange={(event) => update("slug", event.target.value)}
                />
              </Field>

              <Field label="Title" issues={issuesByField.get("title")} className="field-span">
                <input
                  className="field-input"
                  value={draft.title}
                  placeholder="Bounded Async Worker Pool"
                  onChange={(event) => update("title", event.target.value)}
                />
              </Field>

              <Field label="Summary" issues={issuesByField.get("summary")} className="field-span">
                <input
                  className="field-input"
                  value={draft.summary}
                  placeholder="One sentence shown in lists."
                  onChange={(event) => update("summary", event.target.value)}
                />
              </Field>

              <Field label="Module" issues={issuesByField.get("module")}>
                <input
                  className="field-input"
                  value={draft.module}
                  onChange={(event) => update("module", event.target.value)}
                />
              </Field>

              <Field label="Difficulty" issues={issuesByField.get("difficulty")} hint="Selects scoring weights.">
                <select
                  className="field-input"
                  value={draft.difficulty}
                  onChange={(event) => update("difficulty", event.target.value)}
                >
                  {DIFFICULTIES.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </Field>

              <Field label="Level" issues={issuesByField.get("level")}>
                <select
                  className="field-input"
                  value={draft.level}
                  onChange={(event) => update("level", event.target.value)}
                >
                  {LEVELS.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </Field>

              <Field label="Order in track" issues={issuesByField.get("order_index")}>
                <input
                  className="field-input"
                  type="number"
                  min={0}
                  value={draft.order_index}
                  onChange={(event) => update("order_index", Number(event.target.value))}
                />
              </Field>

              <Field label="Points (XP)" issues={issuesByField.get("points")}>
                <input
                  className="field-input"
                  type="number"
                  min={0}
                  value={draft.points}
                  onChange={(event) => update("points", Number(event.target.value))}
                />
              </Field>

              <Field label="Python version" issues={issuesByField.get("python_version")}>
                <input
                  className="field-input"
                  value={draft.python_version}
                  onChange={(event) => update("python_version", event.target.value)}
                />
              </Field>

              <Field label="Time limit (ms)" issues={issuesByField.get("time_limit_ms")} hint="Clamped to the platform ceiling.">
                <input
                  className="field-input"
                  type="number"
                  min={100}
                  value={draft.time_limit_ms}
                  onChange={(event) => update("time_limit_ms", Number(event.target.value))}
                />
              </Field>

              <Field label="Memory limit (MB)" issues={issuesByField.get("memory_limit_mb")} hint="Clamped to the platform ceiling.">
                <input
                  className="field-input"
                  type="number"
                  min={16}
                  value={draft.memory_limit_mb}
                  onChange={(event) => update("memory_limit_mb", Number(event.target.value))}
                />
              </Field>

              <Field
                label="Skills"
                issues={issuesByField.get("skills")}
                hint="Comma-separated dotted ids, e.g. async.asyncio, backend"
                className="field-span"
              >
                <input
                  className="field-input"
                  value={draft.skills.join(", ")}
                  placeholder="async.asyncio, async.concurrency"
                  onChange={(event) => update("skills", splitList(event.target.value))}
                />
              </Field>

              <Field
                label="Tags"
                issues={issuesByField.get("tags")}
                hint="Comma-separated, free-form discovery tags."
                className="field-span"
              >
                <input
                  className="field-input"
                  value={draft.tags.join(", ")}
                  placeholder="asyncio, concurrency, backpressure"
                  onChange={(event) => update("tags", splitList(event.target.value))}
                />
              </Field>
            </div>
          </Card>

          <Card className="authoring-editors">
            <div className="editor-tabs" role="tablist" aria-label="Challenge content">
              <TabButton current={tab} value="description" onSelect={setTab}>
                Description
              </TabButton>
              <TabButton current={tab} value="starter" onSelect={setTab}>
                Starter
              </TabButton>
              <TabButton current={tab} value="visible" onSelect={setTab}>
                Visible tests
              </TabButton>
              <TabButton current={tab} value="hidden" onSelect={setTab}>
                Hidden tests
              </TabButton>
            </div>

            {tab === "description" ? (
              <div className="editor-pane-host">
                <Field label="" issues={issuesByField.get("description")}>
                  <textarea
                    className="field-input editor-textarea"
                    value={draft.description}
                    placeholder={"# Title\n\nOne paragraph of framing.\n\n## Your task\n\n…"}
                    onChange={(event) => update("description", event.target.value)}
                  />
                </Field>
              </div>
            ) : tab === "starter" ? (
              <CodeEditor
                value={draft.starter_code}
                issues={issuesByField.get("starter_code")}
                onChange={(value) => update("starter_code", value)}
              />
            ) : (
              <TestBucket
                bucket={tab === "visible" ? "visible_tests" : "hidden_tests"}
                files={tab === "visible" ? draft.visible_tests : draft.hidden_tests}
                issuesByField={issuesByField}
                onChange={(name, source) =>
                  updateTest(tab === "visible" ? "visible_tests" : "hidden_tests", name, source)
                }
                onRename={(from, to) =>
                  renameTest(tab === "visible" ? "visible_tests" : "hidden_tests", from, to)
                }
                onAdd={() => addTest(tab === "visible" ? "visible_tests" : "hidden_tests")}
                onRemove={(name) => removeTest(tab === "visible" ? "visible_tests" : "hidden_tests", name)}
              />
            )}
          </Card>
        </div>

        <aside className="authoring-side" aria-label="Catalogue">
          <CataloguePanel catalogue={catalogue} />
        </aside>
      </div>
    </div>
  );
}

function splitList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item !== "");
}

function Field({
  label,
  hint,
  issues,
  className = "",
  children,
}: {
  label: string;
  hint?: string;
  issues?: ValidationIssue[] | undefined;
  className?: string;
  children: ReactNode;
}) {
  const error = issues?.find((issue) => issue.severity === "error");
  const warning = issues?.find((issue) => issue.severity === "warning");
  const tone = error !== undefined ? " has-error" : warning !== undefined ? " has-warning" : "";

  return (
    <div className={`field ${className}${tone}`.trim()}>
      {label !== "" && <label className="field-label">{label}</label>}
      {children}
      {hint !== undefined && error === undefined && <p className="field-hint">{hint}</p>}
      {error !== undefined && <p className="field-issue">{error.message}</p>}
      {error === undefined && warning !== undefined && (
        <p className="field-issue field-issue-warning">{warning.message}</p>
      )}
    </div>
  );
}

function TabButton({
  current,
  value,
  onSelect,
  children,
}: {
  current: Tab;
  value: Tab;
  onSelect: (tab: Tab) => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={current === value}
      className={`editor-tab${current === value ? " is-active" : ""}`}
      onClick={() => onSelect(value)}
    >
      {children}
    </button>
  );
}

function CodeEditor({
  value,
  issues,
  onChange,
}: {
  value: string;
  issues?: ValidationIssue[] | undefined;
  onChange: (value: string) => void;
}) {
  const error = issues?.find((issue) => issue.severity === "error");
  const theme = useResolvedTheme();
  return (
    <div className="editor-pane-host">
      {error !== undefined && <Notice tone="danger">{error.message}</Notice>}
      <Editor
        height="420px"
        language="python"
        theme={monacoThemeName(theme)}
        value={value}
        beforeMount={registerPyCraftTheme}
        onChange={(next) => onChange(next ?? "")}
        options={{
          fontSize: 13,
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          tabSize: 4,
          insertSpaces: true,
          automaticLayout: true,
          padding: { top: 12, bottom: 12 },
        }}
      />
    </div>
  );
}

function TestBucket({
  bucket,
  files,
  issuesByField,
  onChange,
  onRename,
  onAdd,
  onRemove,
}: {
  bucket: "visible_tests" | "hidden_tests";
  files: Record<string, string>;
  issuesByField: Map<string, ValidationIssue[]>;
  onChange: (name: string, source: string) => void;
  onRename: (from: string, to: string) => void;
  onAdd: () => void;
  onRemove: (name: string) => void;
}) {
  const names = Object.keys(files);
  const [active, setActive] = useState<string>(names[0] ?? "");

  // Keep the selection valid when a file is added or removed.
  useEffect(() => {
    if (names.length > 0 && !names.includes(active)) setActive(names[0] ?? "");
  }, [names, active]);

  const hint =
    bucket === "visible_tests"
      ? "Shown to the learner. Name them test_*.py."
      : "Graded only, never sent to the browser. Name them test_hidden*.py, and make them catch a plausible naive solution.";

  return (
    <div className="test-bucket">
      <p className="bucket-hint">{hint}</p>
      <div className="bucket-tabs">
        {names.map((name) => (
          <span key={name} className={`bucket-tab${name === active ? " is-active" : ""}`}>
            <button type="button" className="bucket-name" onClick={() => setActive(name)}>
              {name}
            </button>
            {names.length > 1 && (
              <button
                type="button"
                className="bucket-remove"
                aria-label={`Remove ${name}`}
                onClick={() => onRemove(name)}
              >
                ×
              </button>
            )}
          </span>
        ))}
        <Button variant="ghost" onClick={onAdd}>
          + Add file
        </Button>
      </div>

      {active !== "" && (
        <>
          <div className="bucket-name-edit">
            <label className="field-label" htmlFor={`rename-${bucket}`}>
              File name
            </label>
            <input
              id={`rename-${bucket}`}
              className="field-input"
              value={active}
              onChange={(event) => {
                const next = event.target.value;
                if (next !== active) {
                  onRename(active, next);
                  setActive(next);
                }
              }}
            />
          </div>
          <CodeEditor
            value={files[active] ?? ""}
            issues={issuesByField.get(bucket)}
            onChange={(value) => onChange(active, value)}
          />
        </>
      )}
    </div>
  );
}

function ValidationPanel({ result }: { result: ValidationResult }) {
  if (result.issues.length === 0) {
    return <Notice tone="success">No problems found — this draft is ready to publish.</Notice>;
  }
  return (
    <Card className="validation-panel">
      <CardHeader
        title={
          <span>
            {result.error_count} error{result.error_count === 1 ? "" : "s"}, {result.warning_count}{" "}
            warning{result.warning_count === 1 ? "" : "s"}
          </span>
        }
        action={result.valid ? <Badge tone="success">Publishable</Badge> : <Badge tone="danger">Blocked</Badge>}
      />
      <ul className="issue-list">
        {result.issues.map((issue, index) => (
          <li key={`${issue.field}-${index}`} className={`issue issue-${issue.severity}`}>
            <code className="issue-field">{issue.field}</code>
            <span className="issue-message">{issue.message}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

/** A challenge id is `<track>-<slug>`; both halves are needed for the route. */
function draftPath(entry: AuthoringCatalogueEntry): string {
  const slug = entry.id.startsWith(`${entry.track}-`)
    ? entry.id.slice(entry.track.length + 1)
    : entry.id;
  return `/authoring/${entry.track}/${slug}`;
}

function CataloguePanel({ catalogue }: { catalogue: ReturnType<typeof useApi<AuthoringCatalogue>> }) {
  if (catalogue.loading) {
    return (
      <Card>
        <CardHeader title="Catalogue" />
        <Skeleton height="1rem" />
      </Card>
    );
  }
  const data = catalogue.data;
  if (data === null) {
    return (
      <Card>
        <CardHeader title="Catalogue" />
        <p className="muted">{catalogue.error ?? "Unavailable"}</p>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader title={`Catalogue · ${data.total}`} />
      {data.load_errors.length > 0 && (
        <Notice tone="warning">{data.load_errors.length} content problem(s) on disk.</Notice>
      )}
      <ul className="catalogue-list">
        {data.challenges.map((entry) => (
          <li key={entry.id}>
            <Link to={draftPath(entry)} className="catalogue-item">
              <span className="catalogue-title">{entry.title}</span>
              <span className="catalogue-meta">
                {entry.track} · {entry.visible_tests}v/{entry.hidden_tests}h · {entry.points} XP
              </span>
            </Link>
          </li>
        ))}
      </ul>
      {data.empty_tracks.length > 0 && (
        <details className="catalogue-empty">
          <summary>Empty tracks ({data.empty_tracks.length})</summary>
          <ul>
            {data.empty_tracks.map((track) => (
              <li key={track}>
                <code>{track}</code>
              </li>
            ))}
          </ul>
        </details>
      )}
    </Card>
  );
}

function AuthoringSkeleton() {
  return (
    <div className="authoring">
      <div className="authoring-bar">
        <Skeleton height="1.5rem" width="240px" />
      </div>
      <div className="authoring-body">
        <div className="authoring-form">
          <Card>
            <Skeleton height="1rem" />
            <div className="auth-loading-gap" />
            <Skeleton height="1rem" width="80%" />
          </Card>
        </div>
      </div>
    </div>
  );
}
