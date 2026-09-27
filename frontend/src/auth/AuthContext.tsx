/**
 * Session state for the whole app.
 *
 * The provider owns exactly one piece of truth — the signed-in user — and every
 * page reads it through `useAuth()`. Tokens themselves live in the token store;
 * this module only decides when they are written and when the user is fetched.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { api, ApiError, refreshSession } from "../api/client";
import type { TokenResponse, UserProfile } from "../api/client";
import * as tokenStore from "./tokenStore";

export type AuthStatus = "loading" | "authenticated" | "anonymous";

export interface AuthContextValue {
  user: UserProfile | null;
  status: AuthStatus;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  updateProfile: (patch: Parameters<typeof api.updateMe>[0]) => Promise<UserProfile>;
  /** Adopt tokens handed over by an external flow (the GitHub redirect). */
  acceptTokens: (tokens: TokenResponse) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");
  // Tracks whether the provider is still mounted, so an in-flight restore
  // cannot write state after teardown (StrictMode double-invokes the effect).
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const adopt = useCallback((tokens: TokenResponse) => {
    tokenStore.set(tokens);
    setUser(tokens.user);
    setStatus("authenticated");
  }, []);

  const goAnonymous = useCallback(() => {
    tokenStore.clear();
    setUser(null);
    setStatus("anonymous");
  }, []);

  /** Load the profile with the stored token, refreshing once if needed. */
  const restore = useCallback(async () => {
    const stored = tokenStore.get();
    if (stored === null) {
      if (mounted.current) setStatus("anonymous");
      return;
    }

    try {
      const profile = await api.getMe();
      setUser(profile);
      setStatus("authenticated");
      return;
    } catch (cause) {
      // A dead network is not proof the session ended: keep the tokens so the
      // user is not signed out by a transient blip.
      if (cause instanceof ApiError && cause.status === 0) {
        setUser(null);
        setStatus("anonymous");
        return;
      }
    }

    const refreshed = await refreshSession();
    if (!refreshed) {
      tokenStore.clear();
      if (mounted.current) {
        setUser(null);
        setStatus("anonymous");
      }
      return;
    }

    try {
      const profile = await api.getMe();
      if (!mounted.current) return;
      setUser(profile);
      setStatus("authenticated");
    } catch {
      tokenStore.clear();
      if (mounted.current) {
        setUser(null);
        setStatus("anonymous");
      }
    }
  }, []);

  useEffect(() => {
    void restore();
  }, [restore]);

  const login = useCallback(
    async (email: string, password: string) => {
      adopt(await api.login({ email, password }));
    },
    [adopt],
  );

  const register = useCallback(
    async (email: string, password: string, displayName: string) => {
      adopt(await api.register({ email, password, display_name: displayName }));
    },
    [adopt],
  );

  /**
   * End the session locally even when the API call fails.
   *
   * A user who asked to sign out must not stay signed in because the backend
   * was unreachable — the stored refresh token is discarded regardless.
   */
  const logout = useCallback(async () => {
    const refreshToken = tokenStore.getRefreshToken();
    if (refreshToken !== null) {
      try {
        await api.logout(refreshToken);
      } catch {
        // Intentionally ignored: local sign-out proceeds either way.
      }
    }
    goAnonymous();
  }, [goAnonymous]);

  const refreshUser = useCallback(async () => {
    try {
      setUser(await api.getMe());
      setStatus("authenticated");
    } catch (cause) {
      if (cause instanceof ApiError && (cause.status === 401 || cause.status === 403)) {
        goAnonymous();
        return;
      }
      throw cause;
    }
  }, [goAnonymous]);

  const updateProfile = useCallback(async (patch: Parameters<typeof api.updateMe>[0]) => {
    const profile = await api.updateMe(patch);
    setUser(profile);
    return profile;
  }, []);

  const acceptTokens = useCallback(
    async (tokens: TokenResponse) => {
      adopt(tokens);
      // The redirect carries the user already; a refresh keeps it authoritative.
      try {
        const profile = await api.getMe();
        if (mounted.current) setUser(profile);
      } catch {
        // Keep the profile from the token response.
      }
    },
    [adopt],
  );

  const value = useMemo<AuthContextValue>(
    () => ({ user, status, login, register, logout, refreshUser, updateProfile, acceptTokens }),
    [user, status, login, register, logout, refreshUser, updateProfile, acceptTokens],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error("useAuth() must be used inside an <AuthProvider>");
  }
  return context;
}
