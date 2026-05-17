"use client";

/**
 * 주간 업무일지 — 프로젝트/영업 상세 link.
 * admin만 활성화, 비admin은 plain text (사용자 결정 2026-05-11).
 *
 * PR-AI — app/weekly-report/page.tsx에서 추출.
 */

import Link from "next/link";

import { useAuth } from "@/components/AuthGuard";

export function ProjectLink({
  id,
  children,
}: {
  id: string;
  children: React.ReactNode;
}) {
  const { user } = useAuth();
  if (!id || user?.role !== "admin") return <>{children}</>;
  // PR-FM (사용자 요청): 주간 일지 컨텍스트 보존 — 새 탭에서 열기.
  return (
    <Link
      href={`/projects/${encodeURIComponent(id)}`}
      target="_blank"
      rel="noreferrer"
      className="text-blue-700 underline-offset-2 hover:underline dark:text-blue-400"
    >
      {children}
    </Link>
  );
}

export function SaleLink({
  id,
  children,
}: {
  id: string;
  children: React.ReactNode;
}) {
  const { user } = useAuth();
  if (!id || user?.role !== "admin") return <>{children}</>;
  // PR-FM (사용자 요청): 새 탭에서 열기. from 파라미터는 옛 모달 복귀 흐름 위해 유지.
  return (
    <Link
      href={`/sales?sale=${encodeURIComponent(id)}&from=${encodeURIComponent("/weekly-report")}`}
      target="_blank"
      rel="noreferrer"
      className="text-emerald-700 underline-offset-2 hover:underline dark:text-emerald-400"
    >
      {children}
    </Link>
  );
}
