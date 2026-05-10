"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

interface Props {
  /** 자동 redirect 할 경로 (기본: 대시보드) */
  targetPath?: string;
  /** toast 메시지 (기본: "권한이 없습니다.") */
  message?: string;
  /** redirect까지 대기 시간 ms (기본: 1500) */
  delayMs?: number;
}

/**
 * 권한 부족 시 1.5초간 안내 표시 후 자동 redirect.
 * 페이지 진입 직후 user.role 체크에서 거절된 경우에 사용.
 *
 * 사용 예:
 *   if (user && !allowed) return <UnauthorizedRedirect targetPath="/" />;
 */
export default function UnauthorizedRedirect({
  targetPath = "/",
  message = "권한이 없습니다.",
  delayMs = 1500,
}: Props) {
  const router = useRouter();
  const [secondsLeft, setSecondsLeft] = useState(Math.ceil(delayMs / 1000));

  useEffect(() => {
    const redirectTimer = window.setTimeout(() => {
      router.push(targetPath);
    }, delayMs);
    const tickTimer = window.setInterval(() => {
      setSecondsLeft((s) => Math.max(0, s - 1));
    }, 1000);
    return () => {
      window.clearTimeout(redirectTimer);
      window.clearInterval(tickTimer);
    };
  }, [router, targetPath, delayMs]);

  return (
    <main className="flex min-h-[60vh] items-center justify-center p-6">
      <div className="rounded-xl border border-amber-500/40 bg-amber-500/5 px-6 py-5 text-center shadow-sm">
        <p className="text-sm font-medium text-amber-700 dark:text-amber-300">
          {message}
        </p>
        <p className="mt-1 text-xs text-zinc-500">
          잠시 후 자동으로 이동합니다 ({secondsLeft}초)
        </p>
      </div>
    </main>
  );
}
