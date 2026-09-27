/**
 * Typed client for the PyCraft API.
 *
 * Every response shape mirrors the backend's Pydantic schemas; keeping them in
 * one place means a contract change surfaces as a compile error rather than a
 * runtime surprise.
 */

import * as tokenStore from "../auth/tokenStore";

const API_PREFIX = "/api/v1";

// --- auth contracts ------------------------------------------------------
export type UserRole = "learner" | "author" | "admin";

export interface UserProfile {
  id: string;
  email: string;
  display_name: string;
  role: UserRole | string;
  avatar_url: string;
  headline: string;
  bio: string;
  location: string;
  website: string;
  xp: number;
  current_streak: number;
  longest_streak: number;
  last_active_date: string | null;
  is_admin: boolean;
  has_password: boolean;
  linked_providers: string[];
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: UserProfile;
}

export interface SessionInfo {
  id: string;
  provider: string;
  user_agent: string;
  ip_address: string;
  created_at: string;
  last_used_at: string;
  expires_at: string;
  is_current: boolean;
}

export interface AuthConfig {
  password_auth_enabled: boolean;
  registration_enabled: boolean;
  github_enabled: boolean;
  min_password_length: number;
}

export interface MessageResponse {
  message: string;
}

export interface RegisterPayload {
  email: string;
  password: string;
  display_name: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

/** Only provided keys are applied by the API; empty strings clear a field. */
export interface ProfileUpdatePayload {
  display_name?: string;
  headline?: string;
  bio?: string;
  location?: string;
  website?: string;
}

export interface ChangePasswordPayload {
  current_password: string;
  password: string;
}

export interface ResetRequestPayload {
  email: string;
}

export interface ResetConfirmPayload {
  token: string;
  password: string;
}

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
  kind: string;
  is_project: boolean;
}

export interface ChallengeDetail extends ChallengeSummary {
  description: string;
  starter_code: string;
  entry_file: string;
  time_limit_ms: number;
  memory_limit_mb: number;
  visible_tests: Record<string, string>;
  /** Filename -> source, for every file the learner may edit. */
  starter_files: Record<string, string>;
  /** Why the project is scored as it is; grading stays test-driven. */
  rubric: RubricEntry[];
}

export interface RubricEntry {
  label: string;
  weight: number;
  description: string;
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

interface RequestOptions {
  /**
   * Attach the bearer token and allow one refresh-and-retry on a 401. Set to
   * `false` for endpoints that are themselves responsible for credentials
   * (sign in, refresh) so they can never recurse into the refresh flow.
   */
  authenticated?: boolean;
}

/**
 * In-flight refresh, shared so concurrent 401s rotate the token once.
 *
 * Refresh tokens are single-use: two parallel rotations would look like token
 * replay to the backend and revoke every session on the account.
 */
let refreshInFlight: Promise<boolean> | null = null;

async function request<T>(
  path: string,
  init?: RequestInit,
  options: RequestOptions = {},
): Promise<T> {
  const authenticated = options.authenticated ?? true;

  let response = await send(path, init, authenticated ? tokenStore.getAccessToken() : null);

  if (response.status === 401 && authenticated && tokenStore.getRefreshToken() !== null) {
    const refreshed = await refreshSession();
    if (refreshed) {
      // Exactly one retry: a second 401 is a real authorization failure.
      response = await send(path, init, tokenStore.getAccessToken());
    }
  }

  if (!response.ok) {
    // A rejected session must not linger in storage, or every later request
    // repeats the same doomed round trip.
    if (response.status === 401 && authenticated) tokenStore.clear();
    throw new ApiError(await readErrorMessage(response), response.status);
  }
  return (await response.json()) as T;
}

async function send(path: string, init: RequestInit | undefined, token: string | null): Promise<Response> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token !== null) headers["Authorization"] = `Bearer ${token}`;

  try {
    return await fetch(`${API_PREFIX}${path}`, {
      headers,
      ...init,
    });
  } catch {
    throw new ApiError("Cannot reach the PyCraft API. Is the backend running?", 0);
  }
}

/**
 * Rotate the session token pair, storing the result.
 *
 * Returns `false` when there is no refresh token or the backend rejected it, in
 * which case the stored credentials are cleared.
 */
export async function refreshSession(): Promise<boolean> {
  refreshInFlight ??= performRefresh().finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

async function performRefresh(): Promise<boolean> {
  const refreshToken = tokenStore.getRefreshToken();
  if (refreshToken === null) return false;

  try {
    const tokens = await request<TokenResponse>(
      "/auth/refresh",
      { method: "POST", body: JSON.stringify({ refresh_token: refreshToken }) },
      { authenticated: false },
    );
    tokenStore.set(tokens);
    return true;
  } catch {
    tokenStore.clear();
    return false;
  }
}

/**
 * Absolute-in-app URL that starts the GitHub OAuth browser redirect.
 *
 * The backend sends the browser to `redirect_to` after the exchange, appending
 * the tokens as a URL fragment. That path must therefore be the callback page,
 * which knows how to consume and strip the fragment; the user's real
 * destination travels alongside it in `next`.
 */
export function githubAuthorizeUrl(next = "/"): string {
  const callback = `${GITHUB_CALLBACK_PATH}?next=${encodeURIComponent(next)}`;
  return `${API_PREFIX}/auth/github/authorize?redirect_to=${encodeURIComponent(callback)}`;
}

/** Route that reads the OAuth fragment. Shared so both sides agree on the path. */
export const GITHUB_CALLBACK_PATH = "/auth/callback";

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
  // --- auth --------------------------------------------------------------
  getAuthConfig: (): Promise<AuthConfig> => request<AuthConfig>("/auth/config"),

  register: (payload: RegisterPayload): Promise<TokenResponse> =>
    request<TokenResponse>(
      "/auth/register",
      { method: "POST", body: JSON.stringify(payload) },
      { authenticated: false },
    ),

  login: (payload: LoginPayload): Promise<TokenResponse> =>
    request<TokenResponse>(
      "/auth/login",
      { method: "POST", body: JSON.stringify(payload) },
      { authenticated: false },
    ),

  logout: (refreshToken: string): Promise<MessageResponse> =>
    request<MessageResponse>(
      "/auth/logout",
      { method: "POST", body: JSON.stringify({ refresh_token: refreshToken }) },
      { authenticated: false },
    ),

  getMe: (): Promise<UserProfile> => request<UserProfile>("/auth/me"),

  updateMe: (payload: ProfileUpdatePayload): Promise<UserProfile> =>
    request<UserProfile>("/auth/me", { method: "PATCH", body: JSON.stringify(payload) }),

  changePassword: (payload: ChangePasswordPayload): Promise<MessageResponse> =>
    request<MessageResponse>("/auth/me/password", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  listSessions: (): Promise<SessionInfo[]> => request<SessionInfo[]>("/auth/me/sessions"),

  revokeSession: (sessionId: string): Promise<MessageResponse> =>
    request<MessageResponse>(`/auth/me/sessions/${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
    }),

  requestPasswordReset: (payload: ResetRequestPayload): Promise<MessageResponse> =>
    request<MessageResponse>(
      "/auth/password/reset-request",
      { method: "POST", body: JSON.stringify(payload) },
      { authenticated: false },
    ),

  confirmPasswordReset: (payload: ResetConfirmPayload): Promise<MessageResponse> =>
    request<MessageResponse>(
      "/auth/password/reset-confirm",
      { method: "POST", body: JSON.stringify(payload) },
      { authenticated: false },
    ),

  // --- content -----------------------------------------------------------
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
