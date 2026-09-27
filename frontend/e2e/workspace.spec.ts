/**
 * The challenge workspace — the heart of the product.
 *
 * Run and Submit are asynchronous: the POST returns 202 and the client polls
 * until the submission reaches a terminal state. These tests therefore wait on
 * rendered results rather than on a response, which is also what a learner
 * experiences.
 */

import { expect, test } from "@playwright/test";
import { GREET_SOLUTION, HELLO_WORLD_ID, HELLO_WORLD_PATH } from "./config";
import { fillEditor, signInAs, waitForDraft } from "./helpers";

/** Run and wait for the raw output panel. */
async function run(page: import("@playwright/test").Page): Promise<void> {
  await page.getByRole("button", { name: /^▶\s*Run$/ }).click();
  await expect(page.locator(".run-output")).toBeVisible({ timeout: 45_000 });
}

/** Submit and wait for the graded results panel. */
async function submit(page: import("@playwright/test").Page): Promise<void> {
  await page.getByRole("button", { name: "Submit", exact: true }).click();
  await expect(page.locator(".score-number")).toBeVisible({ timeout: 45_000 });
}

test("the workspace shows the briefing and the starter code", async ({ page }) => {
  await signInAs(page);

  await page.goto(HELLO_WORLD_PATH);
  await expect(page.locator(".workspace-title")).toHaveText("Hello, World");

  // The briefing states the contract the tests grade against.
  const briefing = page.getByRole("region", { name: "Challenge briefing" });
  await expect(briefing).toContainText("Hello, <name>!");

  // The editor is seeded with the starter, not left blank.
  await expect(page.locator(".monaco-editor").first()).toBeVisible();
  await expect(page.locator(".view-lines").first()).toContainText("greet");
  await expect(page.locator(".view-lines").first()).toContainText("NotImplementedError");
});

test("Run executes the code and reports its output", async ({ page }) => {
  await signInAs(page);
  await page.goto(HELLO_WORLD_PATH);
  await expect(page.locator(".workspace-title")).toBeVisible();

  // The shipped starter raises, so Run must surface the traceback as stdout
  // with a non-zero exit rather than claiming success.
  await run(page);
  const stdout = page.locator('[data-stream="stdout"]');
  await expect(stdout).toContainText("NotImplementedError");
  await expect(page.locator(".run-meta")).toContainText("exit 1");

  // Replacing it with a working solution flips Run to a pass.
  await fillEditor(page, GREET_SOLUTION);
  await run(page);
  await expect(page.locator(".run-output")).toContainText("3 passed");
});

test("Submit grades only a correct solution at full marks", async ({ page }) => {
  await signInAs(page);
  await page.goto(HELLO_WORLD_PATH);
  await expect(page.locator(".workspace-title")).toBeVisible();

  // The untouched starter fails every test, so scoring must not be generous.
  await submit(page);
  await expect(page.locator(".score-number")).toHaveText("0");
  await expect(page.locator(".score-summary")).toContainText("8 of 8 tests failed");

  // Per-test results are listed, with the visible ones explained and the
  // hidden ones deliberately withheld.
  const visible = page.locator(".test-group", { hasText: "Visible tests" });
  await expect(visible.locator(".test-item")).toHaveCount(3);
  await expect(visible.locator(".test-item[data-status='failed']")).toHaveCount(3);
  await expect(visible.locator(".test-message").first()).toContainText("NotImplementedError");

  const hidden = page.locator(".test-group", { hasText: "Hidden tests" });
  await expect(hidden.locator(".badge")).toHaveText("0/5");
  await expect(hidden.locator(".test-message")).toHaveCount(0);

  // Now the real solution: full marks, every test green.
  await fillEditor(page, GREET_SOLUTION);
  await submit(page);
  await expect(page.locator(".score-number")).toHaveText("100");
  await expect(page.locator(".score-summary")).toContainText("all 8 tests passed");
  await expect(page.locator(".test-item[data-status='passed']")).toHaveCount(8);
  await expect(page.locator(".test-item[data-status='failed']")).toHaveCount(0);
});

test("the editor keeps the learner's work across a reload", async ({ page }) => {
  await signInAs(page);
  await page.goto(HELLO_WORLD_PATH);
  await expect(page.locator(".workspace-title")).toBeVisible();

  const solution = 'def greet(name: str) -> str:\n    return "Hello, draft!"\n';
  await fillEditor(page, solution);
  // The draft is written on a debounce, so wait for that exact content rather
  // than racing the write (or matching the starter, which is saved first).
  await waitForDraft(page, HELLO_WORLD_ID, "solution.py", "Hello, draft!");

  // Drafts are persisted locally, so an accidental refresh must not lose work.
  await page.reload();
  await expect(page.locator(".view-lines").first()).toContainText("Hello, draft!");
  // The starter must have been replaced, not merely followed by the new code.
  await expect(page.locator(".view-lines").first()).not.toContainText("NotImplementedError");
});
