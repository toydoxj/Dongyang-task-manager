"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { consumeCallbackFragment } from "@/lib/auth";

const SSO_SILENT_SUCCESS = "sso_silent_success";
const SSO_SILENT_FAILED = "sso_silent_failed";

export default function WorksCallbackPage() {
  const search = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const inIframe = typeof window !== "undefined" && window.self !== window.top;

    // silent 흐름 실패: backend가 #silent_error=login_required 같은 fragment로 redirect
    if (typeof window !== "undefined") {
      const hash = window.location.hash.startsWith("#")
        ? window.location.hash.slice(1)
        : window.location.hash;
      const params = new URLSearchParams(hash);
      const silentError = params.get("silent_error");
      if (silentError && inIframe) {
        try {
          window.parent.postMessage(
            { type: SSO_SILENT_FAILED, reason: silentError },
            window.location.origin,
          );
        } catch {
          // 무시
        }
        return;
      }
    }

    const queryError = search?.get("error");
    if (queryError) {
      setError(queryError);
      return;
    }

    const result = consumeCallbackFragment();
    if (!result) {
      if (inIframe) {
        // fragment에 token/user 없으면 silent 실패로 간주
        try {
          window.parent.postMessage(
            { type: SSO_SILENT_FAILED, reason: "no_token" },
            window.location.origin,
          );
        } catch {
          // 무시
        }
        return;
      }
      setError("로그인 정보가 없습니다. 다시 시도해 주세요.");
      return;
    }

    // silent SSO 성공: parent에 token/user 전달, parent가 saveAuth + reload
    if (inIframe) {
      try {
        window.parent.postMessage(
          {
            type: SSO_SILENT_SUCCESS,
            token: result.token,
            user: result.user,
            next: result.next,
          },
          window.location.origin,
        );
      } catch {
        // 무시
      }
      return;
    }

    // normal SSO: hard navigate로 AuthGuard 새로 mount → ready phase
    window.location.replace(result.next || "/");
  }, [search]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950 px-4">
      <div className="w-full max-w-sm rounded-xl border border-zinc-800 bg-zinc-900 p-6 text-center">
        {error ? (
          <>
            <p className="text-sm font-medium text-red-400">로그인 실패</p>
            <p className="mt-2 text-xs text-zinc-400">{error}</p>
            <a
              href="/login"
              className="mt-4 inline-block text-xs text-zinc-300 underline-offset-2 hover:underline"
            >
              로그인 화면으로 돌아가기
            </a>
          </>
        ) : (
          <p className="text-sm text-zinc-400">로그인 처리 중...</p>
        )}
      </div>
    </div>
  );
}
