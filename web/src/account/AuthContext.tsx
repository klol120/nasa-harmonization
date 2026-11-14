import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { AccountError, type AuthConfig, type Me, api, getToken, setToken } from "./client";

interface AuthState {
  /** Server settings (which sign-in methods exist). Null while loading or if the server is unreachable. */
  config: AuthConfig | null;
  me: Me | null;
  /** True until the first /auth/me answer (only when a stored session exists). */
  loading: boolean;
  signInWithGoogle: (credential: string) => Promise<void>;
  signInDev: (email: string, name?: string) => Promise<void>;
  signOut: () => Promise<void>;
  deleteAccount: () => Promise<void>;
  refresh: () => Promise<void>;
  /** Opens the sign-in dialog (rendered once, by App). `reason` explains why sign-in is useful there. */
  requestSignIn: (reason?: string) => void;
  signInRequest: { reason?: string } | null;
  closeSignIn: () => void;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(!!getToken());
  const [signInRequest, setSignInRequest] = useState<{ reason?: string } | null>(null);

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setMe(null);
      setLoading(false);
      return;
    }
    try {
      setMe(await api.me());
    } catch (e) {
      if (e instanceof AccountError && e.status === 401) {
        setToken(null);
        setMe(null);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    api.config().then(setConfig, () => setConfig(null));
    refresh();
  }, [refresh]);

  const finish = useCallback(
    async (token: string) => {
      setToken(token);
      await refresh();
      setSignInRequest(null);
    },
    [refresh],
  );

  const value = useMemo<AuthState>(
    () => ({
      config,
      me,
      loading,
      refresh,
      signInRequest,
      requestSignIn: (reason) => setSignInRequest({ reason }),
      closeSignIn: () => setSignInRequest(null),
      signInWithGoogle: async (credential) => finish((await api.google(credential)).token),
      signInDev: async (email, name) => finish((await api.devLogin(email, name)).token),
      signOut: async () => {
        try {
          await api.logout();
        } finally {
          setToken(null);
          setMe(null);
        }
      },
      deleteAccount: async () => {
        await api.deleteAccount();
        setToken(null);
        setMe(null);
      },
    }),
    [config, me, loading, refresh, signInRequest, finish],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}
