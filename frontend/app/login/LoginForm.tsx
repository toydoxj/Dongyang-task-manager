"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { worksLoginUrl } from "@/lib/auth";

interface Props {
  // 호환을 위해 유지하되 사용 안 함
  isSetup?: boolean;
  onSuccess?: () => void;
  worksEnabled?: boolean;
}

export default function LoginForm({ worksEnabled }: Props) {
  const search = useSearchParams();
  const errorMessage = search?.get("error") ?? null;
  const [autoRedirected, setAutoRedirected] = useState(false);

  useEffect(() => {
    // 에러로 돌아온 케이스 또는 SSO 비활성 시에는 자동 redirect 금지 (무한 루프 방지)
    if (errorMessage) return;
    if (!worksEnabled) return;
    if (autoRedirected) return;
    setAutoRedirected(true);
    window.location.replace(worksLoginUrl("/"));
  }, [errorMessage, worksEnabled, autoRedirected]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950 px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">
            (주)동양구조
          </p>
          <h1 className="mt-2 text-xl font-semibold text-white">업무관리 시스템</h1>
        </div>

        <div className="space-y-4 rounded-xl border border-zinc-800 bg-zinc-900 p-6">
          {errorMessage ? (
            <>
              <h2 className="text-center text-sm font-semibold text-red-300">
                로그인 실패
              </h2>
              <p className="rounded-md border border-red-700/40 bg-red-500/5 px-3 py-2 text-center text-xs text-red-300">
                {errorMessage}
              </p>
              <p className="text-center text-xs text-zinc-500">
                회사 NAVER WORKS 계정으로만 로그인할 수 있습니다.
              </p>
              {worksEnabled && (
                <a
                  href={worksLoginUrl("/")}
                  className="block w-full rounded-lg border border-emerald-700/40 bg-emerald-600/10 py-2.5 text-center text-sm font-medium text-emerald-300 transition hover:bg-emerald-600/20"
                >
                  다시 시도
                </a>
              )}
            </>
          ) : worksEnabled ? (
            <>
              <h2 className="text-center text-sm font-semibold text-zinc-300">
                로그인 중...
              </h2>
              <p className="text-center text-xs text-zinc-500">
                회사 NAVER WORKS 로그인 화면으로 이동합니다.
                <br />
                잠시만 기다려 주세요.
              </p>
              {/* 자동 redirect가 실패할 경우의 수동 fallback (JS 비활성화 환경 등) */}
              <a
                href={worksLoginUrl("/")}
                className="block w-full rounded-lg border border-emerald-700/40 bg-emerald-600/10 py-2.5 text-center text-sm font-medium text-emerald-300 transition hover:bg-emerald-600/20"
              >
                이동되지 않으면 클릭
              </a>
            </>
          ) : (
            <>
              <h2 className="text-center text-sm font-semibold text-zinc-300">
                로그인
              </h2>
              <p className="rounded-md border border-amber-700/40 bg-amber-500/5 px-3 py-2 text-center text-xs text-amber-300">
                SSO 설정이 활성화되지 않았습니다. 관리자에게 문의해 주세요.
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
