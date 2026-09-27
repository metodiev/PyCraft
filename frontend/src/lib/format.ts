/**
 * Date formatting for session and account metadata.
 *
 * `Intl.RelativeTimeFormat` is used directly rather than a date library: the
 * app needs two phrasings, not a dependency.
 */

const RELATIVE = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

const STEPS: readonly (readonly [Intl.RelativeTimeFormatUnit, number])[] = [
  ["second", 60],
  ["minute", 60],
  ["hour", 24],
  ["day", 7],
  ["week", 4.348],
  ["month", 12],
  ["year", Number.POSITIVE_INFINITY],
];

/** Parse an ISO timestamp or date, tolerating a missing timezone (SQLite). */
function toDate(value: string): Date | null {
  if (value === "") return null;

  // A bare date is a calendar day, not an instant: build it in local time so it
  // never renders as the previous day for users west of UTC.
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (dateOnly !== null) {
    const date = new Date(
      Number(dateOnly[1]),
      Number(dateOnly[2]) - 1,
      Number(dateOnly[3]),
    );
    return Number.isNaN(date.getTime()) ? null : date;
  }

  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(value);
  const date = new Date(hasZone ? value : `${value}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** "3 minutes ago" / "in 2 days"; empty string when the value is unusable. */
export function formatRelative(value: string, from: Date = new Date()): string {
  const date = toDate(value);
  if (date === null) return "";

  let delta = (date.getTime() - from.getTime()) / 1000;
  for (const [unit, limit] of STEPS) {
    if (Math.abs(delta) < limit) {
      return RELATIVE.format(Math.round(delta), unit);
    }
    delta /= limit;
  }
  return "";
}

/** "27 September 2026" — used for join dates and session expiry. */
export function formatDate(value: string): string {
  const date = toDate(value);
  if (date === null) return "";
  return date.toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" });
}

export function formatDateTime(value: string): string {
  const date = toDate(value);
  if (date === null) return "";
  return date.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Condense a User-Agent header into something legible in a session list.
 *
 * The full string is shown in a `title`; this is the one-line summary.
 */
export function describeUserAgent(userAgent: string): string {
  if (userAgent.trim() === "") return "Unknown client";

  const browser =
    match(userAgent, /Edg\/[\d.]+/, "Edge") ??
    match(userAgent, /OPR\/[\d.]+/, "Opera") ??
    match(userAgent, /Chrome\/[\d.]+/, "Chrome") ??
    match(userAgent, /Firefox\/[\d.]+/, "Firefox") ??
    match(userAgent, /Version\/[\d.]+.*Safari/, "Safari") ??
    match(userAgent, /curl\/[\d.]+/, "curl") ??
    match(userAgent, /python-httpx\/[\d.]+/i, "httpx") ??
    match(userAgent, /Python\/[\d.]+/, "Python") ??
    "Unknown client";

  const platform =
    match(userAgent, /Mac OS X/, "macOS") ??
    match(userAgent, /Windows NT/, "Windows") ??
    match(userAgent, /Android/, "Android") ??
    match(userAgent, /iPhone|iPad/, "iOS") ??
    match(userAgent, /Linux/, "Linux");

  return platform === null ? browser : `${browser} on ${platform}`;
}

function match(userAgent: string, pattern: RegExp, label: string): string | null {
  return pattern.test(userAgent) ? label : null;
}
