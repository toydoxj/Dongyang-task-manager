"use client";

/**
 * 주간 업무일지 — 프로젝트/영업 상세 link.
 * admin만 활성화, 비admin은 plain text (사용자 결정 2026-05-11).
 *
 * PR-AI — app/weekly-report/page.tsx에서 추출.
 * PR-FM — 새 탭에서 열기.
 * PR-FN — 새 탭 → 팝업 윈도우.
 * PR-FO — 공통 PopupLinks (다른 페이지와 일관) 위임.
 */

import { useAuth } from "@/components/AuthGuard";
import {
  ProjectPopupLink,
  SalePopupLink,
} from "@/components/common/PopupLinks";

export function ProjectLink({
  id,
  children,
}: {
  id: string;
  children: React.ReactNode;
}) {
  const { user } = useAuth();
  if (!id || user?.role !== "admin") return <>{children}</>;
  return <ProjectPopupLink id={id}>{children}</ProjectPopupLink>;
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
  return (
    <SalePopupLink id={id} from="/weekly-report">
      {children}
    </SalePopupLink>
  );
}
