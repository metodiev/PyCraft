/**
 * The authoring studio is role-gated.
 *
 * Two things matter and both are covered here: a learner must not be offered
 * authoring at all, and an author/admin must actually be able to use it. The
 * gate is enforced by the API, so this also proves the browser reflects the
 * server's decision rather than a hard-coded flag.
 */

import { expect, test } from "@playwright/test";
import { signInAs, signInAsAdmin } from "./helpers";

test("an admin sees the authoring entry and can open the studio", async ({ page }) => {
  await signInAsAdmin(page);

  // The nav entry only appears once the API confirms the role, so wait for it.
  const navEntry = page.getByRole("link", { name: "Authoring" });
  await expect(navEntry).toBeVisible({ timeout: 20_000 });
  await navEntry.click();

  await expect(page.locator(".authoring-title")).toHaveText("New challenge");
  // The studio is real, not an empty shell: the catalogue is loaded from disk
  // and the content editors are present.
  await expect(page.locator(".card-title", { hasText: "Catalogue" })).toBeVisible();
  await expect(page.getByRole("tablist", { name: "Challenge content" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Validate" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Publish" })).toBeVisible();
});

test("a learner is not offered authoring and is refused the page", async ({ page }) => {
  await signInAs(page);

  // Give the access check time to resolve, then assert the entry is absent
  // rather than merely not-yet-rendered.
  await expect(page.locator(".user-menu-trigger")).toBeVisible();
  await page.waitForLoadState("networkidle");
  await expect(page.getByRole("link", { name: "Authoring" })).toHaveCount(0);

  // Deep-linking to the studio must not grant access either.
  await page.goto("/authoring");
  await expect(page.locator(".authoring-denied")).toContainText("Authoring requires");
  await expect(page.locator(".authoring-denied")).toContainText("learner");
  await expect(page.getByRole("button", { name: "Publish" })).toHaveCount(0);
});
