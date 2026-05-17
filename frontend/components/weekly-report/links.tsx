"use client";

/**
 * 주간 업무일지 — 프로젝트/영업 상세 link.
 * admin만 활성화, 비admin은 plain text (사용자 결정 2026-05-11).
 *
 * PR-AI — app/weekly-report/page.tsx에서 추출.
 * PR-FM — 새 탭에서 열기.
 * PR-FN — 새 탭 → 팝업 윈도우 (사용자 요청). window.open + width/height로 Chrome이 팝업 처리.
 */

import { useAuth } from "@/components/AuthGuard";

const POPUP_FEATURES = "popup=yes,width=1200,height=900,noopener,noreferrer";

function openPopup(href: string): void {
  // window.open이 popup blocker로 차단되면 null 반환 — fallback으로 새 탭.
  const w = window.open(href, "_blank", POPUP_FEATURES);
  if (!w) {
    // 차단된 경우 일반 navigation으로 fallback (새 탭).
    window.open(href, "_blank", "noopener,noreferrer");
  }
}

export function ProjectLink({
  id,
  children,
}: {
  id: string;
  children: React.ReactNode;
}) {
  const { user } = useAuth();
  if (!id || user?.role !== "admin") return <>{children}</>;
  const href = `/projects/${encodeURIComponent(id)}`;
  return (
    <a
      href={href}
      onClick={(e) => {
        e.preventDefault();
        openPopup(href);
      }}
      className="cursor-pointer text-blue-700 underline-offset-2 hover:underline dark:text-blue-400"
    >
      {children}
    </a>
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
  const href = `/sales?sale=${encodeURIComponent(id)}&from=${encodeURIComponent("/weekly-report")}`;
  return (
    <a
      href={href}
      onClick={(e) => {
        e.preventDefault();
        openPopup(href);
      }}
      className="cursor-pointer text-emerald-700 underline-offset-2 hover:underline dark:text-emerald-400"
    >
      {children}
    </a>
  );
}
