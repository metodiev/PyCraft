/**
 * Catalogue and dashboard — the learner's sense of progress.
 *
 * The dashboard is the product's "am I getting anywhere?" screen, so the point
 * of these tests is not that numbers render, but that a genuinely successful
 * submission moves them.
 */

import { expect, test } from "@playwright/test";
import { HELLO_WORLD_ID, HELLO_WORLD_PATH, GREET_SOLUTION } from "./config";
import { fillEditor, signInAs } from "./helpers";

/** Read the three headline figures as label → value, e.g. `{ XP: "0", ... }`. */
async function stats(page: import("@playwright/test").Page): Promise<Record<string, string>> {
  return page.locator(".journey-stats .stat").evaluateAll((elements) =>
    Object.fromEntries(
      elements.map((element) => [
        element.querySelector(".stat-label")?.textContent?.trim() ?? "",
        element.querySelector(".stat-value")?.textContent?.trim() ?? "",
      ]),
    ),
  );
}

/** `"1 / 35"` → `1`. */
function completedCount(value: string | undefined): number {
  return Number.parseInt(value?.split("/")[0]?.trim() ?? "", 10);
}

test("the catalogue lists the challenge library", async ({ page }) => {
  await signInAs(page);

  await page.goto("/challenges");
  await expect(page.getByRole("heading", { name: "Challenges" })).toBeVisible();

  // A real challenge from disk is listed, with its metadata.
  const helloWorld = page.locator(".challenge-card", { hasText: "Hello, World" });
  await expect(helloWorld).toBeVisible();
  await expect(helloWorld).toHaveAttribute("data-completed", "false");
  await expect(helloWorld).toContainText("Getting Started");

  // Nothing is complete for a brand-new account.
  await expect(page.locator(".list-sub")).toContainText("0 of");
  await expect(page.locator(".challenge-card").first()).toBeVisible();
  expect(await page.locator(".challenge-card").count()).toBeGreaterThan(10);

  // Clicking through opens the workspace for that challenge.
  await helloWorld.click();
  await expect(page).toHaveURL(new RegExp(`${HELLO_WORLD_ID}$`));
  await expect(page.locator(".workspace-title")).toHaveText("Hello, World");
});

test("a successful submission moves the dashboard progress", async ({ page }) => {
  await signInAs(page);

  // Baseline: a fresh account has no progress and no history.
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Junior" })).toBeVisible();
  const before = await stats(page);
  expect(completedCount(before["Completed"])).toBe(0);
  expect(before["XP"]).toBe("0");
  await expect(page.getByText("No submissions yet")).toBeVisible();

  // Solve the challenge for real, through the UI.
  await page.goto(HELLO_WORLD_PATH);
  await expect(page.locator(".workspace-title")).toBeVisible();
  await fillEditor(page, GREET_SOLUTION);
  await page.getByRole("button", { name: "Submit", exact: true }).click();
  await expect(page.locator(".score-number")).toHaveText("100", { timeout: 45_000 });

  // The dashboard must reflect it: exactly one more challenge, and real XP.
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Junior" })).toBeVisible();
  const after = await stats(page);
  expect(completedCount(after["Completed"])).toBe(completedCount(before["Completed"]) + 1);
  expect(Number(after["XP"])).toBeGreaterThan(0);

  // The submission is now in the history table, graded and scored.
  const row = page.locator(".data-table tbody tr").first();
  await expect(row).toContainText("Hello, World");
  await expect(row).toContainText("submit");
  await expect(row).toContainText("100");

  // And the catalogue now marks it complete with its best score.
  await page.goto("/challenges");
  const helloWorld = page.locator(".challenge-card", { hasText: "Hello, World" });
  await expect(helloWorld).toHaveAttribute("data-completed", "true");
  await expect(helloWorld.locator(".challenge-card-score")).toHaveText("100/100");
});

test("a failed submission does not move progress", async ({ page }) => {
  await signInAs(page);

  // Submit the untouched starter, which raises NotImplementedError.
  await page.goto(HELLO_WORLD_PATH);
  await expect(page.locator(".workspace-title")).toBeVisible();
  await page.getByRole("button", { name: "Submit", exact: true }).click();
  await expect(page.locator(".score-number")).toHaveText("0", { timeout: 45_000 });

  // Recording the attempt must not be mistaken for completing it.
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Junior" })).toBeVisible();
  expect(completedCount((await stats(page))["Completed"])).toBe(0);
  expect((await stats(page))["XP"]).toBe("0");

  await page.goto("/challenges");
  const helloWorld = page.locator(".challenge-card", { hasText: "Hello, World" });
  await expect(helloWorld).toHaveAttribute("data-completed", "false");
});
