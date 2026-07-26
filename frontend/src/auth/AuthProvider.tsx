import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import { tokenStore } from "./tokenStore";
import {
  loginWithCredentials,
  logout as clearSession,
  refreshSession,
  currentUserFromStore,
  msUntilAccessTokenExpiry,
  InvalidCredentialsError,
} from "./session";
import type { AuthUser } from "./types";

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  status: AuthStatus;
  user: AuthUser | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/** Refresh this long before actual expiry, so a request in flight doesn't
 * race an access token that expires mid-request. Floored at 5s so a
 * clock skew / already-near-expiry token still schedules something. */
const REFRESH_SKEW_MS = 60_000;
const MIN_REFRESH_DELAY_MS = 5_000;

export function AuthProvider({ children }: { children: ReactNode }) {
  // SSR-safe: server and first client render must produce the same
  // markup, so this always starts at "loading" and resolves in an
  // effect (client-only, after tokenStore has real localStorage access).
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<AuthUser | null>(null);
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearRefreshTimer = useCallback(() => {
    if (refreshTimerRef.current !== null) {
      clearTimeout(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }
  }, []);

  const scheduleRefresh = useCallback(() => {
    clearRefreshTimer();
    const msUntilExpiry = msUntilAccessTokenExpiry();
    if (msUntilExpiry === null) return;
    const delay = Math.max(msUntilExpiry - REFRESH_SKEW_MS, MIN_REFRESH_DELAY_MS);
    refreshTimerRef.current = setTimeout(() => {
      void refreshSession();
    }, delay);
  }, [clearRefreshTimer]);

  const syncFromStore = useCallback(() => {
    const current = currentUserFromStore();
    setUser(current);
    setStatus(current ? "authenticated" : "unauthenticated");
    if (current) scheduleRefresh();
    else clearRefreshTimer();
  }, [scheduleRefresh, clearRefreshTimer]);

  useEffect(() => {
    syncFromStore();
    const unsubscribe = tokenStore.subscribe(syncFromStore);
    return () => {
      unsubscribe();
      clearRefreshTimer();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = useCallback(
    async (username: string, password: string) => {
      try {
        const authenticatedUser = await loginWithCredentials(username, password);
        setUser(authenticatedUser);
        setStatus("authenticated");
        scheduleRefresh();
      } catch (err) {
        if (err instanceof InvalidCredentialsError) throw err;
        throw new InvalidCredentialsError();
      }
    },
    [scheduleRefresh],
  );

  const logout = useCallback(() => {
    clearSession();
    // tokenStore.clearTokens() (inside clearSession) notifies subscribers,
    // which re-runs syncFromStore -- no need to setStatus/setUser here too.
  }, []);

  return (
    <AuthContext.Provider value={{ status, user, login, logout }}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth() must be used within an AuthProvider");
  return ctx;
}
