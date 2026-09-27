/**
 * Typed client for the PyCraft API.
 *
 * Every response shape mirrors the backend's Pydantic schemas; keeping them in
 * one place means a contract change surfaces as a compile error rather than a
 * runtime surprise.
 */

const API_PREFIX = "/api/v1";

export interface ChallengeSummary {
  id: string;
  title: string;
  summary: string;
  difficulty: string;
  track: string;
  module: string;
  level: string;
  python_version: string;
  points: number;
  order_index: number;
  skills: string[];
  tags: string[];
  visible_test_count: number;
  skill_mastery: number;
  completed: boolean;
  best_score: number;
}

export interface ChallengeDetail extends ChallengeSummary {
  description: string;
  starter_code: string;
  entry_file: string;
  time_limit_ms: number;
  memory_limit_mb: number;
  visible_tests: Record<string, string>;
}

export interface ProgressSummary {
  xp: number;
  level_id: string;
  level_label: string;
  xp_into_level: number;
  next_level_label: string | null;
  next_level_xp: number | null;
  completed_challenges: number;
  total_challenges: number;
  completion_pct: number;
}

export interface SkillBar {
  skill: string;
  label: string;
  mastery: number;
  xp: number;
  challenges_completed: number;
  challenges_total: number;
}

export interface RoadmapStage {
  id: string;
  title: string;
  description: string;
  level: string;
  progress_pct: number;
  total_challenges: number;
  completed_challenges: number;
  locked: boolean;
}

export interface RecentSubmission {
  id: string;
  challenge_id: string;
  challenge_title: string;
  kind: string;
  status: string;
  score: number | null;
  passed: number;
  failed: number;
  total_tests: number;
  execution_time_ms: number | null;
  created_at: string;
}

export interface Dashboard {
  progress: ProgressSummary;
  skills: SkillBar[];
  roadmap: RoadmapStage[];
  recent_submissions: RecentSubmission[];
  recommended_challenge: ChallengeSummary | null;
  continue_challenge: ChallengeSummary | null;
}

export interface TestResult {
  name: string;
  status: "passed" | "failed" | "error" | "skipped" | string;
  duration_ms: number;
  message: string;
  hidden: boolean;
}

export interface ScoringDimension {
  name: string;
  score: number;
  weight: number;
  detail: string;
}

export interface RunResult {
  submission_id: string;
  status: string;
  stdout: string;
  stderr: string;
  exit_code: number | null;
  execution_time_ms: number;
  memory_used_mb: number;
}

export interface SubmitResult {
  submission_id: string;
  status: string;
  score: number;
  passed: number;
  failed: number;
  total_tests: number;
  execution_time_ms: number;
  memory_used_mb: number;
  results: TestResult[];
  dimensions: ScoringDimension[];
  summary: string;
  progress: ProgressSummary | null;
}

export interface RuntimeInfo {
  execution_backend: string;
  python_versions: string[];
  default_python_version: string;
  environment: string;
  challenge_count: number;
}

/** Error carrying the HTTP status so callers can react to 404/422/503. */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_PREFIX}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ApiError("Cannot reach the PyCraft API. Is the backend running?", 0);
  }

  if (!response.ok) {
    throw new ApiError(await readErrorMessage(response), response.status);
  }
  return (await response.json()) as T;
}

/** Extract the most useful message from FastAPI's error shapes. */
async function readErrorMessage(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "detail" in body) {
      const { detail } = body as { detail: unknown };
      if (typeof detail === "string") return detail;
      if (Array.isArray(detail)) {
        const first = detail[0] as { msg?: string } | undefined;
        if (first?.msg) return first.msg;
      }
    }
  } catch {
    // Fall through to the generic message.
  }
  return `Request failed with status ${response.status}`;
}

export const api = {
  getRuntime: (): Promise<RuntimeInfo> => request<RuntimeInfo>("/runtime"),

  listChallenges: (track?: string): Promise<ChallengeSummary[]> =>
    request<ChallengeSummary[]>(track ? `/challenges?track=${encodeURIComponent(track)}` : "/challenges"),

  getChallenge: (id: string): Promise<ChallengeDetail> =>
    request<ChallengeDetail>(`/challenges/${encodeURIComponent(id)}`),

  getDashboard: (): Promise<Dashboard> => request<Dashboard>("/dashboard"),

  getRoadmap: (): Promise<RoadmapStage[]> => request<RoadmapStage[]>("/roadmap"),

  getSkills: (): Promise<SkillBar[]> => request<SkillBar[]>("/skills"),

  getProgress: (): Promise<ProgressSummary> => request<ProgressSummary>("/progress"),

  run: (challengeId: string, files: Record<string, string>): Promise<RunResult> =>
    request<RunResult>(`/challenges/${encodeURIComponent(challengeId)}/run`, {
      method: "POST",
      body: JSON.stringify({ files }),
    }),

  submit: (challengeId: string, files: Record<string, string>): Promise<SubmitResult> =>
    request<SubmitResult>(`/challenges/${encodeURIComponent(challengeId)}/submit`, {
      method: "POST",
      body: JSON.stringify({ files }),
    }),
};
