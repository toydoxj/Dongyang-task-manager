"use client";

import { usePathname } from "next/navigation";
import { createContext, lazy, Suspense, useContext, useEffect, useState } from "react";

import {
  checkAuthStatus,
  getUser,
  isLoggedIn,
  trySilentSSO,
  verifyAndHydrateFromMe,
} from "@/lib/auth";
import type { UserInfo } from "@/lib/types";

const LoginForm = lazy(() => import("@/app/login/LoginForm"));

interface AuthState {
  user: UserInfo | null;
  refresh: () => void;
  driveLocalRoot: string;
}

const AuthContext = createContext<AuthState>({
  user: null,
  refresh: () => {},
  driveLocalRoot: "",
});
export const useAuth = (): AuthState => useContext(AuthContext);

type Phase = "loading" | "login" | "setup" | "ready";

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  // SSO callback 페이지는 인증 처리 중이라 AuthGuard 검사 우회
  const isCallbackPath = pathname?.startsWith("/auth/works/callback") ?? false;

  const [phase, setPhase] = useState<Phase>("loading");
  const [user, setUser] = useState<UserInfo | null>(null);
  const [worksEnabled, setWorksEnabled] = useState(false);
  const [driveLocalRoot, setDriveLocalRoot] = useState("");

  const refresh = (): void => {
    void (async () => {
      // setState는 모두 비동기 callback 내부 (effect의 동기 본문이 아님)
      let needSetup = false;
      let worksOn = false;
      try {
        const status = await checkAuthStatus();
        needSetup = !status.initialized;
        worksOn = !!status.works_enabled;
        setWorksEnabled(worksOn);
        setDriveLocalRoot(status.works_drive_local_root || "");
      } catch {
        // 백엔드가 응답 안 하면 일단 진입은 허용 (네트워크 에러 대비).
        // user는 localStorage에서 채워야 페이지 권한 가드가 정상 동작 (PR Phase 0).
        setUser(getUser());
        setPhase("ready");
        return;
      }
      if (needSetup) {
        setPhase("setup");
        return;
      }
      if (!isLoggedIn()) {
        // 로그인 안 됐고 SSO 활성 + 사용자가 명시 logout한 게 아니라면 silent SSO 시도
        // ?error= query가 있거나 sessionStorage에 logged_out flag면 skip
        const hasError =
          typeof window !== "undefined" &&
          new URLSearchParams(window.location.search).has("error");
        const justLoggedOut =
          typeof window !== "undefined" &&
          window.sessionStorage.getItem("dy_logged_out") === "1";
        if (worksOn && !hasError && !justLoggedOut) {
          const user = await trySilentSSO(window.location.pathname || "/");
          if (user) {
            setUser(user);
            setPhase("ready");
            return;
          }
        }
        setPhase("login");
        return;
      }
      // PR-EM (Phase 4-G 2단계): 부팅 시 cookie validity 검증.
      // verifyAndHydrateFromMe는 raw fetch + credentials:include — silent SSO trigger
      // 안 함(callback 무한 재귀 회피, INCIDENT #4 체크리스트 #1 패턴).
      // 200: 응답 user로 saveAuth 갱신(fragment 시점 schema 변경 자동 정정).
      // 401/network: null. backend down 시에도 graceful — 첫 authFetch 401 → PR-BO
      // silent SSO 1회 retry로 회복. 여기서 login redirect 강제 X (Phase 0-B 정책).
      const verified = await verifyAndHydrateFromMe();
      setUser(verified ?? getUser());
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
      <div className="flex min-h-screen flex-col items-center justify-center gap-2 bg-zinc-950 text-sm text-zinc-400">
        <p>인증 확인 중...</p>
        <p className="text-xs text-zinc-600">잠시 후 자동으로 진행됩니다</p>
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
    <AuthContext.Provider value={{ user, refresh, driveLocalRoot }}>
      {children}
    </AuthContext.Provider>
  );
}
