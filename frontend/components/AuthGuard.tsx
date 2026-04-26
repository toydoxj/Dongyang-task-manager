"use client";

import { createContext, lazy, Suspense, useContext, useEffect, useState } from "react";

import { checkAuthStatus, getUser, isLoggedIn } from "@/lib/auth";
import type { UserInfo } from "@/lib/types";

const LoginForm = lazy(() => import("@/app/login/LoginForm"));

interface AuthState {
  user: UserInfo | null;
  refresh: () => void;
}

const AuthContext = createContext<AuthState>({ user: null, refresh: () => {} });
export const useAuth = (): AuthState => useContext(AuthContext);

type Phase = "loading" | "login" | "setup" | "ready";

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const [phase, setPhase] = useState<Phase>("loading");
  const [user, setUser] = useState<UserInfo | null>(null);

  const refresh = (): void => {
    void (async () => {
      // setState는 모두 비동기 callback 내부 (effect의 동기 본문이 아님)
      let needSetup = false;
      try {
        const status = await checkAuthStatus();
        needSetup = !status.initialized;
      } catch {
        // 백엔드가 응답 안 하면 일단 진입은 허용 (네트워크 에러 대비)
        setPhase("ready");
        return;
      }
      if (needSetup) {
        setPhase("setup");
        return;
      }
      if (!isLoggedIn()) {
        setPhase("login");
        return;
      }
      setUser(getUser());
      setPhase("ready");
    })();
  };

  useEffect(() => {
    refresh();
  }, []);

  if (phase === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-950 text-sm text-zinc-400">
        로딩 중...
      </div>
    );
  }

  if (phase === "login" || phase === "setup") {
    return (
      <Suspense
        fallback={
          <div className="flex min-h-screen items-center justify-center bg-zinc-950 text-sm text-zinc-400">
            로딩 중...
          </div>
        }
      >
        <LoginForm isSetup={phase === "setup"} onSuccess={refresh} />
      </Suspense>
    );
  }

  return (
    <AuthContext.Provider value={{ user, refresh }}>{children}</AuthContext.Provider>
  );
}
