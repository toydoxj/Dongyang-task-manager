"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";

import LoadingState from "@/components/ui/LoadingState";

/**
 * PROJ-005 — 기존 `/project?id=...` 진입을 신규 `/projects/{id}`로 redirect.
 *
 * 외부 hardcoded URL(예: NAVER WORKS Bot 알림, 북마크, 이메일)
 * 호환을 위해 기존 path는 살려두고 client-side replace로 이동.
 * id 없는 진입은 안내 문구만 노출 후 목록 link 제공.
 */
export default function ProjectRedirectPage() {
  return (
    <Suspense fallback={<LoadingState message="이동 중" height="h-32" />}>
      <Inner />
    </Suspense>
  );
}

function Inner() {
  const sp = useSearchParams();
  const router = useRouter();
  const id = sp.get("id");

  useEffect(() => {
    if (id) router.replace(`/projects/${encodeURIComponent(id)}`);
  }, [id, router]);

  if (id) {
    return <LoadingState message="프로젝트 상세로 이동 중" height="h-32" />;
  }
  return (
    <div className="space-y-3">
      <Link href="/projects" className="text-xs text-zinc-500 hover:underline">
        ← 프로젝트 목록
      </Link>
      <p className="rounded-md border border-yellow-500/40 bg-yellow-500/5 p-3 text-sm text-yellow-400">
        프로젝트 ID가 없습니다. 목록에서 카드를 선택하세요.
      </p>
    </div>
  );
}
