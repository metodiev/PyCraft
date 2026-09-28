/**
 * Colour theme.
 *
 * The platform shipped dark-only; light mode is a second set of design tokens
 * selected by `data-theme` on `<html>`. The choice lives on the profile page
 * under Appearance, and these tests pin the behaviour a learner depends on: it
 * is offered there and nowhere else, it applies, it persists, and it reaches
 * the Monaco editor as well as the page chrome.
 *
 * The resolved theme is asserted through `data-theme` rather than by comparing
 * pixels, so a palette tweak cannot break the suite while a genuine regression
 * — the attribute never being set, or the editor ignoring it — still fails it.
 */

import { expect, test, type Page } from "@playwright/test";
import { HELLO_WORLD_PATH } from "./config";
import { signInAs } from "./helpers";

/** The theme actually rendered, read from the element the CSS keys off. */
function resolvedTheme(page: Page): Promise<string | null> {
  return page.evaluate(() => document.documentElement.dataset.theme ?? null);
}

/** The stored choice, or null when following the OS. */
function storedChoice(page: Page): Promise<string | null> {
  return page.evaluate(() => window.localStorage.getItem("pycraft.theme"));
}

/** Monaco paints its own background, so it is the proof the editor switched. */
function editorBackground(page: Page): Promise<string | null> {
  return page.evaluate(() => {
    const host = document.querySelector(".monaco-editor");
    const surface = host?.querySelector(".monaco-editor-background") ?? host;
    return surface ? getComputedStyle(surface).backgroundColor : null;
  });
}

/** Open the Appearance settings and choose a theme. */
async function chooseTheme(page: Page, name: "System" | "Light" | "Dark"): Promise<void> {
  await page.goto("/profile");
  await page.getByRole("heading", { name: "Appearance" }).waitFor();
  await page.getByRole("radio", { name: name, exact: true }).click();
}

test("the switcher lives in the profile settings, not the header", async ({ page }) => {
  await signInAs(page);

  // Signed in on the dashboard: the header must not offer it.
  await expect(page.locator(".app-header").getByRole("radiogroup")).toHaveCount(0);

  await page.goto("/profile");
  await expect(page.getByRole("heading", { name: "Appearance" })).toBeVisible();
  await expect(page.getByRole("radiogroup", { name: "Colour theme" })).toBeVisible();
});

test("the choice applies, persists across reloads, and survives navigation", async ({ page }) => {
  await signInAs(page);

  await chooseTheme(page, "Light");
  await expect.poll(() => resolvedTheme(page)).toBe("light");
  expect(await storedChoice(page)).toBe("light");

  await chooseTheme(page, "Dark");
  await expect.poll(() => resolvedTheme(page)).toBe("dark");
  expect(await storedChoice(page)).toBe("dark");

  // A reload must not flash back to the other theme: the pre-paint script in
  // index.html reads the same key before the app boots.
  await page.reload();
  expect(await resolvedTheme(page)).toBe("dark");

  await page.goto("/challenges");
  expect(await resolvedTheme(page)).toBe("dark");
});

test("system is the default and stores no explicit choice", async ({ page }) => {
  await signInAs(page);

  await chooseTheme(page, "Light");
  await expect.poll(() => storedChoice(page)).toBe("light");

  await page.getByRole("radio", { name: "System", exact: true }).click();
  await expect.poll(() => storedChoice(page)).toBeNull();
  // In every default browser context the OS preference is light.
  await expect.poll(() => resolvedTheme(page)).toBe("light");
});

test("the editor follows the theme, not just the page chrome", async ({ page }) => {
  await signInAs(page);

  await chooseTheme(page, "Light");
  await page.goto(HELLO_WORLD_PATH);
  await page.locator(".monaco-editor").first().waitFor({ state: "visible" });
  // A dark surface here would mean the editor theme never switched even though
  // the page behind it did.
  await expect.poll(() => editorBackground(page)).toBe("rgb(255, 255, 255)");

  await chooseTheme(page, "Dark");
  await page.goto(HELLO_WORLD_PATH);
  await page.locator(".monaco-editor").first().waitFor({ state: "visible" });
  await expect.poll(() => editorBackground(page)).toBe("rgb(13, 17, 23)");
});
