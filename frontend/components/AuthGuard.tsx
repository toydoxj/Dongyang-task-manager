"use client";

import { usePathname } from "next/navigation";
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
  const pathname = usePathname();
  // SSO callback 페이지는 인증 처리 중이라 AuthGuard 검사 우회
  const isCallbackPath = pathname?.startsWith("/auth/works/callback") ?? false;

  const [phase, setPhase] = useState<Phase>("loading");
  const [user, setUser] = useState<UserInfo | null>(null);
  const [worksEnabled, setWorksEnabled] = useState(false);

  const refresh = (): void => {
    void (async () => {
      // setState는 모두 비동기 callback 내부 (effect의 동기 본문이 아님)
      let needSetup = false;
      try {
        const status = await checkAuthStatus();
        needSetup = !status.initialized;
        setWorksEnabled(!!status.works_enabled);
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
      // 로그인 후에도 /login URL에 머물러 있으면 즉시 내 업무로 이동
      if (
        typeof window !== "undefined" &&
        window.location.pathname.startsWith("/login")
      ) {
        window.location.replace("/me");
      }
    })();
  };

  useEffect(() => {
    if (isCallbackPath) return; // callback 페이지가 fragment 처리 + hard navigate
    refresh();
  }, [isCallbackPath]);

  if (isCallbackPath) {
    return <>{children}</>;
  }

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
        <LoginForm
          isSetup={phase === "setup"}
          worksEnabled={worksEnabled}
          onSuccess={refresh}
        />
      </Suspense>
    );
  }

  return (
    <AuthContext.Provider value={{ user, refresh }}>{children}</AuthContext.Provider>
  );
}
