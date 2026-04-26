"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import LoadingState from "@/components/ui/LoadingState";

import ProjectClient from "./ProjectClient";

export default function ProjectPage() {
  return (
    <Suspense fallback={<LoadingState message="페이지 준비 중" height="h-32" />}>
      <Inner />
    </Suspense>
  );
}

function Inner() {
  const sp = useSearchParams();
  const id = sp.get("id");

  if (!id) {
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

  return <ProjectClient id={id} />;
}
