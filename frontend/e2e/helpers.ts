/**
 * Shared helpers for the end-to-end suite.
 *
 * Two rules shape this file:
 *
 * 1. **Every test creates its own account.** Nothing is shared through the
 *    database, so tests cannot influence one another's progress and the suite
 *    passes against a used database as readily as an empty one.
 * 2. **Only real user-visible affordances are used.** The components could not
 *    be given `data-testid` attributes, so everything here drives accessible
 *    roles, real labels and the existing stylesheet hooks.
 */

import { expect, type APIRequestContext, type Page } from "@playwright/test";
import { ADMIN_EMAIL, API_URL, HELLO_WORLD_PATH, PASSWORD } from "./config";
/** A unique address per call, so parallel tests never collide. */
export function uniqueEmail(prefix = "e2e"): string {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
}

export interface Account {
  email: string;
  password: string;
}

/**
 * Create an account straight through the API, bypassing the UI.
 *
 * Registering through the form signs the browser in, which would make "sign in"
 * impossible to test. Creating the account out of band keeps the page
 * anonymous, so the real sign-in form can be exercised.
 *
 * 201 is "created"; 409 means the address already exists, which happens for the
 * fixed admin address in a reused database and is equally fine.
 */
async function createAccount(request: APIRequestContext, email: string): Promise<void> {
  const response = await request.post(`${API_URL}/api/v1/auth/register`, {
    data: { email, password: PASSWORD, display_name: email.split("@")[0] ?? "E2E" },
  });
  const body = await response.text();
  expect(
    [201, 409],
    `registering ${email} returned ${response.status()}: ${body}`,
  ).toContain(response.status());
}

/** Create an account, sign in through the form, and land on the dashboard. */
export async function signInAs(page: Page, email: string = uniqueEmail()): Promise<Account> {
  await createAccount(page.context().request, email);
  return signIn(page, { email, password: PASSWORD });
}

/** Create (if needed) the address the API promotes to admin, then sign in. */
export async function signInAsAdmin(page: Page): Promise<Account> {
  const account = await signInAs(page, ADMIN_EMAIL);

  // `reuseExistingServer` can adopt a server that was started earlier without
  // `PYCRAFT_ADMIN_EMAILS`, and the role is fixed when an address is first
  // registered — so the address would stay a learner and the authoring tests
  // would fail for a reason that has nothing to do with the code under test.
  // Fail with the cause instead of a bare "link not found" twenty seconds later.
  const role = await page.evaluate(async () => {
    const stored = window.localStorage.getItem("pycraft.auth");
    const token = stored ? (JSON.parse(stored) as { access_token?: string }).access_token : null;
    if (!token) return null;
    const response = await fetch("/api/v1/auth/me", {
      headers: { Authorization: `Bearer ${token}` },
    });
    return ((await response.json()) as { role?: string }).role ?? null;
  });
  if (role !== "admin") {
    throw new Error(
      `${ADMIN_EMAIL} signed in as "${role ?? "unknown"}" instead of "admin". ` +
        `Something is already listening on ${API_URL} that was not started with ` +
        `PYCRAFT_ADMIN_EMAILS set — stop it, or let the suite start its own server.`,
    );
  }
  return account;
}

/** Sign in through the real form and wait for the signed-in shell. */
export async function signIn(page: Page, account: Account): Promise<Account> {
  await page.goto("/login");
  await page.getByRole("heading", { name: "Sign in" }).waitFor();
  await page.getByRole("textbox", { name: "Email", exact: true }).fill(account.email);
  await page.getByRole("textbox", { name: "Password", exact: true }).fill(account.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  // The signed-in shell replaces the auth card with the account menu.
  await expect(page.locator(".user-menu-trigger")).toBeVisible({ timeout: 20_000 });
  return account;
}

/**
 * Sign out through the header account menu.
 *
 * The trigger is a plain button, but the item inside the popup is exposed as a
 * `menuitem`, so it cannot be found by role "button".
 */
export async function signOut(page: Page): Promise<void> {
  await page.locator(".user-menu-trigger").click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
}

/** Collapse whitespace so the rendered editor text and the source compare equal. */
function normalize(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

/**
 * Replace the contents of the Monaco editor, and prove the model matches.
 *
 * Monaco is not driven through its textarea. It renders a hidden read-only one
 * and intercepts key handling, so synthetic input is unreliable: a select-all
 * press is dropped, and the insertion that follows **appends** to the starter
 * rather than replacing it. That failure mode is worse than an untidy editor —
 * the submission would be graded on code the learner never wrote, and a test
 * could pass its first assertion while doing it.
 *
 * The loader therefore exposes the editor API on `window.monaco` in dev and
 * test builds, and the model is set directly. That is exact, needs no racing
 * against Monaco's re-render, and is verified against the rendered text so a
 * helper failure can never be mistaken for a wrong submission.
 *
 * `source` is written verbatim — there is no auto-indenting — so callers must
 * pass properly indented Python. See `GREET_SOLUTION`.
 */
export async function fillEditor(page: Page, source: string): Promise<void> {
  await page.locator(".monaco-editor").first().waitFor({ state: "visible" });
  await page.locator(".view-line").first().waitFor();

  const failure = await page.evaluate((text) => {
    const api = (window as Window & { monaco?: MonacoApi }).monaco;
    if (!api) return "monaco is not exposed on window";
    const models = api.editor.getModels();
    const model = models.at(-1);
    if (!model) return "the editor has no model";
    model.setValue(text);
    return null;
  }, source);

  if (failure !== null) throw new Error(`could not set the editor content: ${failure}`);

  // Read the model back, not the DOM: the model is what gets submitted.
  const content = await page.evaluate(() => {
    const api = (window as Window & { monaco?: MonacoApi }).monaco;
    return api?.editor.getModels().at(-1)?.getValue() ?? null;
  });
  expect(normalize(content ?? "")).toBe(normalize(source));
}

/** The slice of the Monaco API these helpers rely on. */
interface MonacoApi {
  editor: {
    getModels: () => {
      getValue: () => string;
      setValue: (value: string) => void;
    }[];
  };
}

/** Open the Hello World workspace and wait for the editor to be ready. */
export async function openHelloWorld(page: Page): Promise<void> {
  await page.goto(HELLO_WORLD_PATH);
  await expect(page.locator(".workspace-title")).toBeVisible();
  await expect(page.locator(".monaco-editor").first()).toBeVisible();
}

/**
 * Wait until the editor's local draft contains `marker`.
 *
 * Drafts are written on a debounce, so reloading straight after typing is a
 * race. Waiting for the stored value is the real precondition of a "work
 * survives a refresh" test, unlike an arbitrary sleep — and matching on the
 * content, not merely the key, avoids passing on the starter that gets saved
 * before the learner has typed anything.
 */
export async function waitForDraft(
  page: Page,
  challengeId: string,
  fileName: string,
  marker: string,
): Promise<void> {
  const key = `pycraft:draft:${challengeId}:${fileName}`;
  await expect
    .poll(() => page.evaluate((storageKey) => window.localStorage.getItem(storageKey), key), {
      timeout: 10_000,
    })
    .toContain(marker);
}
