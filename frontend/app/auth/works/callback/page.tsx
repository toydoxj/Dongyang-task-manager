"use client";

import { useEffect, useState } from "react";

import { consumeCallbackFragment, verifyAndHydrateFromMe } from "@/lib/auth";

const SSO_SILENT_SUCCESS = "sso_silent_success";
const SSO_SILENT_FAILED = "sso_silent_failed";

interface CallbackResolution {
  /** 본문에 표시할 사용자 친화 에러 (null이면 "로그인 처리 중" 노출) */
  displayError: string | null;
  /** iframe 부모로 보낼 메시지 (silent 흐름) */
  silentMessage:
    | { type: string; reason: string }
    | { type: string; token?: string; user?: unknown; next?: string }
    | null;
  /** non-iframe normal SSO 성공 시 redirect 경로 */
  redirect: string | null;
}

/** mount 시 1회 평가 — URL fragment/query + sessionStorage(consumeCallbackFragment) 읽어 결과 결정.
 * useState lazy initializer라 effect 내 setState cascading X. SSR(window 미정의)에서는 idle 상태. */
function resolveCallback(): CallbackResolution {
  if (typeof window === "undefined") {
    return { displayError: null, silentMessage: null, redirect: null };
  }
  const inIframe = window.self !== window.top;

  // silent 흐름 실패 — backend가 #silent_error= fragment로 redirect
  const hash = window.location.hash.startsWith("#")
    ? window.location.hash.slice(1)
    : window.location.hash;
  const hashParams = new URLSearchParams(hash);
  const silentError = hashParams.get("silent_error");
  if (silentError && inIframe) {
    return {
      displayError: null,
      silentMessage: { type: SSO_SILENT_FAILED, reason: silentError },
      redirect: null,
    };
  }

  // ?error=... query (window.location.search 직접 — useSearchParams는 hook이라 사용 불가)
  const queryError = new URLSearchParams(window.location.search).get("error");
  if (queryError) {
    return { displayError: queryError, silentMessage: null, redirect: null };
  }

  // sessionStorage consume — fragment에 담긴 token/user 회수 (idempotent: 두 번째 호출 시 null)
  const result = consumeCallbackFragment();
  if (!result) {
    if (inIframe) {
      return {
        displayError: null,
        silentMessage: { type: SSO_SILENT_FAILED, reason: "no_token" },
        redirect: null,
      };
    }
    return {
      displayError: "로그인 정보가 없습니다. 다시 시도해 주세요.",
      silentMessage: null,
      redirect: null,
    };
  }

  // silent SSO 성공 — parent에 token/user 전달
  if (inIframe) {
    return {
      displayError: null,
      silentMessage: {
        type: SSO_SILENT_SUCCESS,
        token: result.token,
        user: result.user,
        next: result.next,
      },
      redirect: null,
    };
  }

  // normal SSO — hard navigate로 AuthGuard 새로 mount → ready phase
  return {
    displayError: null,
    silentMessage: null,
    redirect: result.next || "/",
  };
}

export default function WorksCallbackPage() {
  // mount 시 1회 결정 (URL/sessionStorage 읽기 + consume). lazy initializer.
  const [resolution] = useState<CallbackResolution>(resolveCallback);

  // 외부 시스템 동기화 (postMessage / window.location)만 effect에 둠. setState 없음.
  useEffect(() => {
    if (resolution.silentMessage) {
      try {
        window.parent.postMessage(resolution.silentMessage, window.location.origin);
      } catch {
        // 무시
      }
    } else if (resolution.redirect) {
      // PR-CY (INCIDENT #1 #4): redirect 직전 cookie 기반 /me로 user 검증·갱신.
      // 401/network 시 graceful fallback (fragment user 그대로 사용). authFetch 미사용 →
      // INCIDENT #4(401 → silent SSO → 무한 재귀) 회피.
      void verifyAndHydrateFromMe().finally(() => {
        window.location.replace(resolution.redirect!);
      });
    }
  }, [resolution]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950 px-4">
      <div className="w-full max-w-sm rounded-xl border border-zinc-800 bg-zinc-900 p-6 text-center">
        {resolution.displayError ? (
          <>
            <p className="text-sm font-medium text-red-400">로그인 실패</p>
            <p className="mt-2 text-xs text-zinc-400">{resolution.displayError}</p>
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
