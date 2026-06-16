import { useEffect, useState } from "react";
import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface AuthUser {
  id: string;
  email: string;
  full_name: string | null;
  role: "commercial" | "admin";
  status: "PENDING" | "ACTIVE" | "REJECTED";
  created_at: string;
}

interface AuthState {
  token: string | null;
  user: AuthUser | null;
  setAuth: (token: string, user: AuthUser) => void;
  clearAuth: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      setAuth: (token, user) => set({ token, user }),
      clearAuth: () => set({ token: null, user: null }),
    }),
    { name: "sma-auth" }
  )
);

/**
 * La réhydratation depuis le localStorage est asynchrone (Promise) même si le
 * storage est synchrone — sans cette garde, les routes peuvent se monter une
 * première fois avec token/user encore à `null` et rediriger au mauvais endroit
 * (ex: admin renvoyé vers /commercial après un refresh).
 */
export function useAuthHydrated(): boolean {
  const [hydrated, setHydrated] = useState(() => useAuthStore.persist.hasHydrated());

  useEffect(() => {
    if (useAuthStore.persist.hasHydrated()) {
      setHydrated(true);
      return;
    }
    return useAuthStore.persist.onFinishHydration(() => setHydrated(true));
  }, []);

  return hydrated;
}
