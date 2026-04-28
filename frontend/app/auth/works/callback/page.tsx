"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { consumeCallbackFragment } from "@/lib/auth";

export default function WorksCallbackPage() {
  const router = useRouter();
  const search = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // 백엔드가 에러를 query로 넘긴 경우 (정상 흐름은 fragment 사용)
    const queryError = search?.get("error");
    if (queryError) {
      setError(queryError);
      return;
    }

    const result = consumeCallbackFragment();
    if (!result) {
      setError("로그인 정보가 없습니다. 다시 시도해 주세요.");
      return;
    }
    router.replace(result.next || "/");
  }, [router, search]);

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
