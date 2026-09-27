/**
 * Shared constants for the end-to-end suite.
 *
 * Both `playwright.config.ts` (which builds the `webServer` commands) and the
 * specs import this module, so the ports the browser is pointed at can never
 * drift from the ports the servers were started on.
 */

/**
 * Ports on purpose outside the usual development pair (API 8000, web 5173).
 * A developer, or a second checkout, is very likely to already own those, and
 * `reuseExistingServer` would then silently test the wrong servers.
 */
export const API_PORT = Number(process.env.E2E_API_PORT ?? 8123);
export const WEB_PORT = Number(process.env.E2E_WEB_PORT ?? 5273);

export const API_URL = `http://127.0.0.1:${API_PORT}`;
export const WEB_URL = `http://127.0.0.1:${WEB_PORT}`;

/**
 * The one address the API promotes to admin (`PYCRAFT_ADMIN_EMAILS`), which is
 * what makes the role-gated authoring studio reachable from a browser.
 *
 * It has to be fixed rather than random because the server needs the value
 * before any test runs, and it must be known to the main process that builds
 * the `webServer` command. Tests register it on demand and treat "already
 * registered" as success, so a database reused between runs is fine.
 *
 * The domain must be one `EmailStr` accepts: `example.com` is allowed, whereas
 * reserved names such as `.test` or `.local` are rejected and would make
 * registration fail with a 422.
 */
export const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? "e2e-author@example.com";

/** Satisfies the server policy: 10+ characters, and it needs a letter and a digit. */
export const PASSWORD = "Playwright-Pass-2026";

/**
 * How to launch the API.
 *
 * Locally the backend has its own virtualenv, so `.venv/bin/uvicorn` is correct
 * and self-contained. CI installs the backend into the runner's interpreter,
 * where that path does not exist, so it overrides this with `python -m uvicorn`.
 */
export const UVICORN = process.env.E2E_UVICORN ?? ".venv/bin/uvicorn";

/** Hello World, whose contract is the formatted string `Hello, <name>!`. */
export const HELLO_WORLD_ID = "python-fundamentals-hello-world";
export const HELLO_WORLD_PATH = `/challenges/${HELLO_WORLD_ID}`;

/**
 * A correct `greet`, written the way a learner would actually type it.
 *
 * This is set on the editor model verbatim, with no auto-indenting, so it is
 * spelled out with real indentation — flat source would be a Python syntax
 * error and the submission would score zero for a reason that has nothing to
 * do with the learner's understanding.
 */
export const GREET_SOLUTION = 'def greet(name: str) -> str:\n    return f"Hello, {name}!"\n';
