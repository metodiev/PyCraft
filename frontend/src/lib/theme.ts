/**
 * Theme selection.
 *
 * The platform shipped dark-only, so every colour already flows through the
 * design tokens; a light theme is a second set of token values plus the code
 * here to pick between them. Nothing in a component should branch on the theme.
 *
 * Three modes are offered rather than two. "System" is the default because it
 * is what a learner expects from an IDE: follow the OS, and only override it
 * deliberately. The resolved value ("light" or "dark") is what actually reaches
 * the DOM, as `data-theme` on `<html>`, and what Monaco is told.
 *
 * The module keeps a tiny listener store rather than React state so the two
 * Monaco editors and the header toggle stay in step, and so a change made in
 * one tab is picked up in another.
 */

import { useSyncExternalStore } from "react";

export type ThemeMode = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

/**
 * Also written as a literal in the pre-paint script in `index.html`, which
 * cannot import this module. Change both together.
 */
export const THEME_STORAGE_KEY = "pycraft.theme";

/**
 * What to use when nothing is stored and the OS preference is unreadable.
 * Dark is the original look, so an unreadable preference degrades to the
 * historical default rather than to an untested one.
 */
const FALLBACK_THEME: ResolvedTheme = "dark";

const LIGHT_QUERY = "(prefers-color-scheme: light)";

type Listener = () => void;
const listeners = new Set<Listener>();

/** Cached so `getSnapshot` returns a stable value between reads. */
let cachedMode: ThemeMode | null = null;
let mediaQuery: MediaQueryList | null = null;
let mediaListenerAttached = false;

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    // Private browsing modes and hardened settings throw on access.
    return null;
  }
}

function isMode(value: unknown): value is ThemeMode {
  return value === "system" || value === "light" || value === "dark";
}

function prefersLight(): boolean {
  try {
    return window.matchMedia(LIGHT_QUERY).matches;
  } catch {
    // No `matchMedia` (or a blocked query): fall back to the default.
    return FALLBACK_THEME === "light";
  }
}

/** The learner's choice, defaulting to following the OS. */
export function getMode(): ThemeMode {
  if (cachedMode !== null) return cachedMode;

  // Defensive: a hand-edited or truncated value must not leave the app on an
  // unrecognised theme, and `localStorage` may be unavailable entirely.
  let stored: string | null = null;
  try {
    stored = storage()?.getItem(THEME_STORAGE_KEY) ?? null;
  } catch {
    stored = null;
  }

  cachedMode = isMode(stored) ? stored : "system";
  return cachedMode;
}

/** Turn a mode into the theme that should actually be rendered. */
export function resolveTheme(mode: ThemeMode = getMode()): ResolvedTheme {
  if (mode === "light" || mode === "dark") return mode;
  return prefersLight() ? "light" : "dark";
}

/** Apply a resolved theme to the document. */
export function applyTheme(theme: ResolvedTheme): void {
  const root = document.documentElement;
  root.dataset["theme"] = theme;
  // Tells the browser how to paint native UI — scrollbars, form controls, the
  // text caret — which CSS cannot reach.
  root.style.colorScheme = theme;
}

export function setMode(next: ThemeMode): void {
  cachedMode = next;
  try {
    if (next === "system") {
      // Absent means "follow the OS", so the key is removed rather than stored
      // as "system": a learner who never chose keeps following a later OS change
      // even if the storage format is ever revised.
      storage()?.removeItem(THEME_STORAGE_KEY);
    } else {
      storage()?.setItem(THEME_STORAGE_KEY, next);
    }
  } catch {
    // Storage full or blocked. The in-memory value still applies for this tab,
    // which is what the learner sees; only persistence is lost.
  }
  applyTheme(resolveTheme(next));
  emit();
}

function emit(): void {
  for (const listener of listeners) listener();
}

function onSystemThemeChange(): void {
  // Only a "system" choice tracks the OS; an explicit choice stays put.
  if (getMode() !== "system") return;
  applyTheme(resolveTheme("system"));
  emit();
}

function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  if (!mediaListenerAttached) {
    mediaListenerAttached = true;
    try {
      mediaQuery = window.matchMedia(LIGHT_QUERY);
      mediaQuery.addEventListener("change", onSystemThemeChange);
    } catch {
      // No live OS-preference tracking; the stored choice still works.
    }
  }
  return () => {
    listeners.delete(listener);
  };
}

/** The learner's choice, re-rendering when it changes. */
export function useThemeMode(): ThemeMode {
  return useSyncExternalStore(subscribe, getMode, () => "system" as ThemeMode);
}

/** The theme actually rendered, re-rendering when the OS or the choice changes. */
export function useResolvedTheme(): ResolvedTheme {
  return useSyncExternalStore(subscribe, resolveTheme, () => FALLBACK_THEME);
}

export function useTheme(): {
  mode: ThemeMode;
  resolved: ResolvedTheme;
  setMode: (next: ThemeMode) => void;
} {
  return { mode: useThemeMode(), resolved: useResolvedTheme(), setMode };
}

/**
 * Name of the Monaco theme for a resolved value.
 *
 * Both themes are registered up front (`lib/monaco.ts`), so switching is just a
 * prop change — no re-registration and no editor remount.
 */
export function monacoThemeName(theme: ResolvedTheme): string {
  return theme === "light" ? "pycraft-light" : "pycraft-dark";
}
