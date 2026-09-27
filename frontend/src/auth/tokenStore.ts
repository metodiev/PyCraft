/**
 * Token persistence for the API client.
 *
 * Kept out of the client itself so request logic stays testable and the storage
 * strategy can change in one place. Every read is defensive: private browsing
 * modes throw on `localStorage`, and a hand-edited value must not brick the app,
 * so unreadable data is discarded and an in-memory copy keeps the session alive
 * for as long as the tab is open.
 */

export interface StoredTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  /** Epoch milliseconds the pair was stored — diagnostics only. */
  stored_at: number;
}

/** What callers may hand to `set()`; missing extras be given defaults. */
export interface TokenInput {
  access_token: string;
  refresh_token: string;
  token_type?: string | undefined;
  expires_in?: number | undefined;
}

const STORAGE_KEY = "pycraft.auth";

/** Mirror of the persisted pair, used when `localStorage` is unavailable. */
let memory: StoredTokens | null = null;

type Listener = () => void;
const listeners = new Set<Listener>();

/**
 * Observe token changes.
 *
 * The provider uses this to notice that a request cleared the pair — a revoked
 * session, or a sign-out in another tab — and drop the user to anonymous state
 * instead of leaving a shell that can no longer load anything.
 */
export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function notify(): void {
  for (const listener of listeners) listener();
}

let resolved = false;
let backing: Storage | null = null;

function storage(): Storage | null {
  if (!resolved) {
    resolved = true;
    backing = probeStorage();
  }
  return backing;
}

function probeStorage(): Storage | null {
  try {
    const candidate = globalThis.localStorage;
    const probe = `${STORAGE_KEY}.probe`;
    candidate.setItem(probe, "1");
    candidate.removeItem(probe);
    return candidate;
  } catch {
    return null;
  }
}

function readRaw(store: Storage | null): string | null {
  if (store === null) return null;
  try {
    return store.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function parseTokens(raw: string): StoredTokens | null {
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof value !== "object" || value === null) return null;

  const candidate = value as Record<string, unknown>;
  const access = candidate["access_token"];
  const refresh = candidate["refresh_token"];
  if (typeof access !== "string" || access === "") return null;
  if (typeof refresh !== "string" || refresh === "") return null;

  const type = candidate["token_type"];
  const expires = candidate["expires_in"];
  const storedAt = candidate["stored_at"];

  return {
    access_token: access,
    refresh_token: refresh,
    token_type: typeof type === "string" ? type : "bearer",
    expires_in: typeof expires === "number" ? expires : 0,
    stored_at: typeof storedAt === "number" ? storedAt : Date.now(),
  };
}

/** Returns the stored pair, or `null` when absent or unusable. */
export function get(): StoredTokens | null {
  const raw = readRaw(storage());
  if (raw === null) return memory;

  const parsed = parseTokens(raw);
  if (parsed === null) {
    // Corrupt entry: drop it rather than failing on every request.
    clear();
    return null;
  }
  return parsed;
}

export function set(tokens: TokenInput): void {
  const record: StoredTokens = {
    access_token: tokens.access_token,
    refresh_token: tokens.refresh_token,
    token_type: tokens.token_type ?? "bearer",
    expires_in: tokens.expires_in ?? 0,
    stored_at: Date.now(),
  };
  memory = record;

  const store = storage();
  if (store !== null) {
    try {
      store.setItem(STORAGE_KEY, JSON.stringify(record));
    } catch {
      // Quota exceeded or storage blocked — the memory copy still serves this tab.
    }
  }
  notify();
}

export function clear(): void {
  // Read the raw value rather than `get()`: a corrupt entry delegates to
  // `clear()`, so going through `get()` here would recurse.
  const hadTokens = memory !== null || readRaw(storage()) !== null;
  memory = null;

  const store = storage();
  if (store !== null) {
    try {
      store.removeItem(STORAGE_KEY);
    } catch {
      // Nothing useful to do; the next read falls back to memory.
    }
  }
  if (hadTokens) notify();
}

export function getAccessToken(): string | null {
  return get()?.access_token ?? null;
}

export function getRefreshToken(): string | null {
  return get()?.refresh_token ?? null;
}
