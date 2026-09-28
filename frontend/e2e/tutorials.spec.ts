/**
 * Tutorials — the reading material beside the catalogue.
 *
 * The product rule these tests protect is that reading is never graded: a
 * tutorial can be marked read, but doing so must not move XP, level or
 * challenge completion. If that ever regresses, the "completion is earned by
 * passing tests" promise is broken.
 */

import { expect, test } from "@playwright/test";
import { signInAs } from "./helpers";

const TUTORIALS_PATH = "/tutorials";

/** Read the visible track labels from the filter chips. */
async function trackLabels(page: import("@playwright/test").Page): Promise<string[]> {
  return page.locator(".track-chip").evaluateAll((elements) =>
    elements.map((element) => element.textContent?.trim() ?? ""),
  );
}

test("the tutorial catalogue lists articles grouped by track", async ({ page }) => {
  await signInAs(page);

  await page.goto(TUTORIALS_PATH);
  await expect(page.getByRole("heading", { name: "Tutorials" })).toBeVisible();

  // Real articles from disk, not placeholders.
  expect(await page.locator(".tutorial-card").count()).toBeGreaterThan(10);

  // Track headings reuse the roadmap's wording, so the two pages agree.
  await expect(
    page.getByRole("heading", { name: "Python Fundamentals", exact: true }),
  ).toBeVisible();

  expect((await trackLabels(page)).length).toBeGreaterThan(2);

  // A brand-new account has read nothing.
  await expect(page.locator(".list-sub")).toContainText("0 read");
  await expect(page.locator(".tutorial-card[data-read='true']")).toHaveCount(0);
});

test("a tutorial renders its article and links to a challenge", async ({ page }) => {
  await signInAs(page);

  await page.goto(TUTORIALS_PATH);
  const card = page.locator(".tutorial-card").first();
  const title = (await card.locator(".tutorial-card-title").textContent())?.trim() ?? "";
  await card.click();

  await expect(page.locator(".tutorial-article h1")).toHaveText(title);

  // The body is rendered as structure, not dumped as raw Markdown source.
  const body = page.locator(".article-body .markdown");
  await expect(body).toBeVisible();
  await expect(body.locator("h2, h3").first()).toBeVisible();
  await expect(body.locator("p").first()).toBeVisible();
  await expect(body).not.toContainText("## ");

  // Articles end with a route into the exercise that applies them.
  const practice = page.locator(".article-practice");
  await expect(practice).toBeVisible();
  await expect(practice.getByRole("link", { name: /Open challenge/ })).toBeVisible();
});

test("marking a tutorial read persists without granting XP", async ({ page }) => {
  await signInAs(page);

  const stat = async (label: string): Promise<string> => {
    return (
      (await page
        .locator(".journey-stats .stat", { hasText: label })
        .locator(".stat-value")
        .textContent()) ?? ""
    );
  };

  await page.goto("/");
  const xpBefore = await stat("XP");

  await page.goto(TUTORIALS_PATH);
  await page.locator(".tutorial-card").first().click();

  await expect(page.locator(".article-actions button")).toHaveText("Mark as read");
  await page.locator(".article-actions button").click();

  // The control flips, and the header reports the article as read.
  await expect(page.locator(".article-actions button")).toHaveText("Mark as unread");
  await expect(page.locator(".article-head").getByText("Read", { exact: true })).toBeVisible();

  // It survives a reload, so it is stored rather than local component state.
  await page.reload();
  await expect(page.locator(".article-actions button")).toHaveText("Mark as unread");

  // The catalogue reflects the coverage.
  await page.goto(TUTORIALS_PATH);
  await expect(page.locator(".list-sub")).toContainText("1 read");
  await expect(page.locator(".tutorial-card[data-read='true']")).toHaveCount(1);

  // Reading is not graded: XP and completion are untouched.
  await page.goto("/");
  expect(await stat("XP")).toBe(xpBefore);
  await expect(page.locator(".journey-stats .stat", { hasText: "Completed" })).toContainText(
    "0 /",
  );

  // Clearing the marker works too, so a careless click is recoverable.
  await page.goto(TUTORIALS_PATH);
  await page.locator(".tutorial-card").first().click();
  await page.locator(".article-actions button").click();
  await expect(page.locator(".article-actions button")).toHaveText("Mark as read");

  await page.goto(TUTORIALS_PATH);
  await expect(page.locator(".list-sub")).toContainText("0 read");
});

test("the track filter narrows the catalogue", async ({ page }) => {
  await signInAs(page);
  await page.goto(TUTORIALS_PATH);

  // Wait for the catalogue to render before counting, or the comparison below
  // races the fetch and compares against zero.
  await expect(page.locator(".tutorial-card").first()).toBeVisible();
  const allCards = await page.locator(".tutorial-card").count();
  expect(allCards).toBeGreaterThan(4);

  await page.locator(".track-chip", { hasText: "Databases" }).click();

  await expect(page).toHaveURL(/track=databases/);
  await expect(page.locator(".track-title")).toHaveCount(1);
  await expect(page.locator(".track-title")).toHaveText("Databases");

  const filtered = page.locator(".tutorial-card");
  await expect(filtered.first()).toBeVisible();

  const filteredCount = await filtered.count();
  expect(filteredCount).toBeGreaterThan(0);
  expect(filteredCount).toBeLessThan(allCards);

  // Clearing the filter restores the full catalogue.
  await page.locator(".track-chip", { hasText: "All tracks" }).click();
  await expect(page.locator(".tutorial-card")).toHaveCount(allCards);
});

test("tutorials sit behind the same guard as the rest of the app", async ({ page }) => {
  // Deep link as a bookmarked URL would, signed out.
  await page.goto(`${TUTORIALS_PATH}?track=databases`);
  await expect(page).toHaveURL(/\/login$/);

  // The guard also covers an individual article.
  await page.goto("/tutorials/python-fundamentals-functions-and-scope");
  await expect(page).toHaveURL(/\/login$/);
});
