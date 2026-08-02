/**
 * SSR-safe token storage primitive. Not React -- this is the one module
 * ApiClient's composition root (src/api/instance.ts) and AuthProvider both
 * depend on, so there is exactly one source of truth for "what tokens do
 * we currently have," never a React-state copy that can drift from
 * localStorage.
 *
 * SSR note: TanStack Start renders this app on the server, where
 * `window`/`localStorage` do not exist. This store starts every server
 * render (and every client render, until hydration reads localStorage
 * once) as "not hydrated" -- callers must treat `getAccessToken() === null`
 * as "unknown, not necessarily unauthenticated" until `isHydrated()` is
 * true. See AuthProvider for how the loading state is derived from this.
 */

interface StoredTokens {
  accessToken: string;
  refreshToken: string;
  /** Not in the JWT payload and there is no GET /auth/me (see
   * docs/FRONTEND_ARCHITECTURE.md §11) -- persisted here so a page reload
   * doesn't lose the username while the token itself is still valid. */
  username: string;
}

const STORAGE_KEY = "radar-eye.auth.tokens";

let tokens: StoredTokens | null = null;
let hydrated = false;
const listeners = new Set<() => void>();

function readFromLocalStorage(): StoredTokens | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as StoredTokens) : null;
  } catch {
    return null;
  }
}

function ensureHydrated(): void {
  if (hydrated || typeof window === "undefined") return;
  tokens = readFromLocalStorage();
  hydrated = true;
}

function notify(): void {
  for (const listener of listeners) listener();
}

export const tokenStore = {
  isHydrated(): boolean {
    return hydrated;
  },

  getAccessToken(): string | null {
    ensureHydrated();
    return tokens?.accessToken ?? null;
  },

  getRefreshToken(): string | null {
    ensureHydrated();
    return tokens?.refreshToken ?? null;
  },

  getUsername(): string | null {
    ensureHydrated();
    return tokens?.username ?? null;
  },

  setTokens(next: StoredTokens): void {
    tokens = next;
    hydrated = true;
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    }
    notify();
  },

  clearTokens(): void {
    tokens = null;
    hydrated = true;
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(STORAGE_KEY);
    }
    notify();
  },

  /** For AuthProvider to re-render on login/logout/forced-logout (401),
   * wherever in the app they originate. */
  subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};
