/**
 * Avatar helpers: initials and a stable colour tone derived from the account.
 *
 * The tone is picked from the design tokens so avatars stay inside the palette;
 * hashing the identifier keeps a user's colour the same across pages.
 */

export type AvatarTone = "accent" | "success" | "warning" | "danger" | "info";

const TONES: readonly AvatarTone[] = ["accent", "success", "warning", "danger", "info"];

/** Up to two initials from a display name, falling back to the email. */
export function initials(name: string, email = ""): string {
  const source = name.trim() === "" ? email.trim() : name.trim();
  if (source === "") return "?";

  const words = source.split(/[\s._-]+/).filter((word) => word !== "");
  const first = words[0] ?? source;
  const second = words.length > 1 ? words[words.length - 1] : undefined;

  const firstLetter = [...first][0] ?? "?";
  if (second === undefined) return firstLetter.toUpperCase();
  const secondLetter = [...second][0] ?? "";
  return `${firstLetter}${secondLetter}`.toUpperCase();
}

export function toneFor(seed: string): AvatarTone {
  let hash = 0;
  for (const char of seed) {
    hash = (hash * 31 + char.codePointAt(0)!) % 100_000;
  }
  return TONES[hash % TONES.length] ?? "accent";
}

/** Providers arrive lower-case from the API; show them in a readable form. */
export function formatProvider(provider: string): string {
  if (provider === "") return "Unknown";
  return provider[0]!.toUpperCase() + provider.slice(1);
}
