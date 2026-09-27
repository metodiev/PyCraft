/**
 * Playwright configuration for the PyCraft end-to-end suite.
 *
 * Playwright starts **both** servers, so the suite is a single command with no
 * setup steps. The API runs with the *local* execution backend: the container
 * sandbox is not available in CI, and executing Python on the host is enough to
 * exercise the learner journey end to end.
 *
 * Two details keep a run hermetic:
 *
 * - The API gets its **own SQLite file**, recreated empty on every run, so a run
 *   never reads or writes the developer's `backend/.pycraft.db` and never needs
 *   a pre-existing database.
 * - The ports are deliberately not the development defaults (API 8000, web
 *   5173), and an existing server is **not** adopted by default — see
 *   `reuseExistingServer` below.
 */

import { defineConfig, devices } from "@playwright/test";
import { ADMIN_EMAIL, API_PORT, API_URL, UVICORN, WEB_PORT, WEB_URL } from "./e2e/config";

/**
 * `PYCRAFT_ADMIN_EMAILS` is a list setting, and pydantic-settings JSON-decodes
 * those from the environment, so the value must be a JSON array. A bare
 * comma-separated string crashes startup with a `SettingsError`.
 */
const ADMIN_EMAILS = JSON.stringify([ADMIN_EMAIL]);

const API_COMMAND = [
  // SQLite will not create the directory the database lives in.
  "mkdir -p ../frontend/e2e/.data &&",
  // Start from an empty database. The admin role is decided when an address is
  // first registered, so a database left over from an earlier run — one made
  // before `PYCRAFT_ADMIN_EMAILS` was set, say — would keep the authoring
  // address a learner and fail the authoring tests for no real reason.
  "rm -f ../frontend/e2e/.data/e2e.db &&",
  "PYCRAFT_ENVIRONMENT=test",
  "PYCRAFT_EXECUTION_BACKEND=local",
  "PYCRAFT_DATABASE_URL=sqlite+aiosqlite:///../frontend/e2e/.data/e2e.db",
  `PYCRAFT_ADMIN_EMAILS='${ADMIN_EMAILS}'`,
  `${UVICORN} app.main:app --port ${API_PORT}`,
].join(" ");

const WEB_COMMAND = `VITE_API_TARGET=${API_URL} npm run dev -- --port ${WEB_PORT} --strictPort`;

/**
 * Whether to adopt a server that is already listening instead of starting one.
 *
 * Off by default, including locally. Reuse looks harmless but quietly changes
 * what is under test: a server left over from an earlier run answers on the
 * port with whatever configuration, database and bundle *it* was started with,
 * and the suite then reports real-looking failures in code that was never
 * loaded. That happened here — an orphaned API from a previous run kept its own
 * database, so the admin account was a learner and two authoring tests failed
 * for no reason in the application.
 *
 * Starting both servers costs a few seconds, which is a good trade for a run
 * that is always about the code in the working tree. Set `E2E_REUSE_SERVER=1`
 * to opt back in when iterating against servers you started on purpose.
 */
const reuseExistingServer = process.env.E2E_REUSE_SERVER === "1";

export default defineConfig({
  testDir: "./e2e",
  // A stray `test.only` would silently skip the rest of the suite in CI.
  forbidOnly: !!process.env.CI,
  // One retry in CI absorbs a genuinely slow first sandbox run; none locally,
  // so a flake is visible rather than hidden.
  retries: process.env.CI ? 1 : 0,
  // Every test registers its own account and never shares state, so the specs
  // are order-independent and may run in parallel.
  fullyParallel: true,
  workers: process.env.CI ? 2 : 4,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  timeout: 60_000,
  expect: { timeout: 15_000 },

  use: {
    baseURL: WEB_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },

  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],

  webServer: [
    {
      command: API_COMMAND,
      cwd: "../backend",
      // `/api/v1/runtime` only answers once the lifespan has indexed the
      // challenge catalogue, so it is a true readiness probe, not just a port
      // check.
      url: `${API_URL}/api/v1/runtime`,
      reuseExistingServer,
      // The first start applies migrations and indexes 35 challenges.
      timeout: 120_000,
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      command: WEB_COMMAND,
      cwd: ".",
      url: WEB_URL,
      reuseExistingServer,
      timeout: 120_000,
      stdout: "pipe",
      stderr: "pipe",
    },
  ],
});
