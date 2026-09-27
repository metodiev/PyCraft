/**
 * Authentication — the entry point to everything else.
 *
 * If these break, nothing behind the guard is reachable, so they exercise the
 * real forms rather than seeding tokens into `localStorage`.
 *
 * Note the deliberate split: accounts are created through the API, because the
 * register form signs the browser in on success and would make sign-in testing
 * impossible. The register form itself is covered by its own test.
 */

import { expect, test } from "@playwright/test";
import { PASSWORD } from "./config";
import { signIn, signInAs, signOut, uniqueEmail } from "./helpers";

test("a new account can register and lands signed in", async ({ page }) => {
  const email = uniqueEmail("register");

  await page.goto("/register");
  await page.getByRole("heading", { name: "Create account" }).waitFor();
  await page.getByRole("textbox", { name: "Email", exact: true }).fill(email);
  await page.getByRole("textbox", { name: "Password", exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();

  // Registering signs the reader in, so the account menu replaces the sign-in
  // link and the dashboard becomes reachable.
  await expect(page.locator(".user-menu-trigger")).toBeVisible({ timeout: 20_000 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Junior" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Sign in" })).toHaveCount(0);
  // The menu shows the account it signed in as.
  await expect(page.locator(".user-menu-name")).toHaveText(email.split("@")[0] ?? "");
});

test("an account can sign out and sign back in", async ({ page }) => {
  const account = await signInAs(page, uniqueEmail("signout"));

  await signOut(page);
  // Signed out, the protected dashboard is no longer reachable.
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible();

  await signIn(page, account);
  await expect(page.locator(".user-menu-trigger")).toBeVisible();
});

test("a wrong password is refused and says so", async ({ page }) => {
  const account = await signInAs(page, uniqueEmail("wrongpass"));
  await signOut(page);

  await page.goto("/login");
  await page.getByRole("heading", { name: "Sign in" }).waitFor();
  await page.getByRole("textbox", { name: "Email", exact: true }).fill(account.email);
  await page.getByRole("textbox", { name: "Password", exact: true }).fill("Wr0ng-Password-1");
  await page.getByRole("button", { name: "Sign in" }).click();

  // The form stays put and reports the failure through an alert region.
  await expect(page.getByRole("alert")).toContainText("Email or password is incorrect");
  await expect(page).toHaveURL(/\/login$/);
});

test("a protected route redirects to login and resumes after sign-in", async ({ page }) => {
  const email = uniqueEmail("deeplink");

  // Deep link straight past the shell, as a bookmarked URL would. The guard
  // must bounce to the sign-in form rather than render a broken page.
  await page.goto("/roadmap");
  await expect(page).toHaveURL(/\/login$/);

  // Signing in must return the reader to the page they actually asked for,
  // not dump them on the dashboard.
  await signInAs(page, email);
  await expect(page).toHaveURL(/\/roadmap$/);
});

test("the register form enforces the password policy", async ({ page }) => {
  await page.goto("/register");
  await page.getByRole("heading", { name: "Create account" }).waitFor();
  await page.getByRole("textbox", { name: "Email", exact: true }).fill(uniqueEmail("policy"));

  const submit = page.getByRole("button", { name: "Create account" });
  await page.getByRole("textbox", { name: "Password", exact: true }).fill("short");
  await expect(submit).toBeDisabled();

  await page.getByRole("textbox", { name: "Password", exact: true }).fill(PASSWORD);
  await expect(submit).toBeEnabled();
});
