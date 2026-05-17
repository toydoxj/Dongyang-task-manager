"use client";

/**
 * 프로젝트·영업 상세를 팝업 윈도우 형태로 여는 공통 link 컴포넌트.
 *
 * PR-FN: weekly-report links.tsx 신설 (팝업 동작).
 * PR-FO (사용자 요청 확장): /me, /projects, /dashboard 등 모든 곳에서 동일 동작이 되도록
 * `components/common/PopupLinks.tsx`로 추출.
 *
 * 모든 list/카드/표의 프로젝트·영업 이름 클릭이 본 컴포넌트를 거치면 일관된 팝업 동작.
 * className 자유로워 호출처 디자인 그대로 유지 가능.
 */

import type React from "react";

import { cn } from "@/lib/utils";

const POPUP_FEATURES = "popup=yes,width=1200,height=900,noopener,noreferrer";

export function openInPopup(href: string): void {
  const w = window.open(href, "_blank", POPUP_FEATURES);
  if (!w) {
    // 팝업 차단 시 새 탭으로 fallback.
    window.open(href, "_blank", "noopener,noreferrer");
  }
}

interface ProjectPopupLinkProps {
  id: string;
  /** 해시(예: "#tasks") 또는 query 등 추가 path suffix. */
  suffix?: string;
  className?: string;
  /** 추가 클릭 동작 — onClick 호출은 stopPropagation/preventDefault 이후 발생. */
  onAfterClick?: () => void;
  children: React.ReactNode;
  /** 디폴트 스타일(blue underline-on-hover) 사용. false면 className만 적용. */
  defaultStyle?: boolean;
  /** 부모 <tr> 등에 onClick이 있는 경우 propagation 막기. 기본 true. */
  stopPropagation?: boolean;
}

export function ProjectPopupLink({
  id,
  suffix,
  className,
  onAfterClick,
  children,
  defaultStyle = true,
  stopPropagation = true,
}: ProjectPopupLinkProps) {
  if (!id) return <>{children}</>;
  const href = `/projects/${encodeURIComponent(id)}${suffix ?? ""}`;
  return (
    <a
      href={href}
      onClick={(e) => {
        if (stopPropagation) e.stopPropagation();
        e.preventDefault();
        openInPopup(href);
        onAfterClick?.();
      }}
      className={cn(
        "cursor-pointer",
        defaultStyle &&
          "text-blue-700 underline-offset-2 hover:underline dark:text-blue-400",
        className,
      )}
    >
      {children}
    </a>
  );
}

interface SalePopupLinkProps {
  id: string;
  /** 닫을 때 복귀할 referrer path. 기본 현재 페이지. */
  from?: string;
  className?: string;
  onAfterClick?: () => void;
  children: React.ReactNode;
  defaultStyle?: boolean;
  stopPropagation?: boolean;
}

export function SalePopupLink({
  id,
  from,
  className,
  onAfterClick,
  children,
  defaultStyle = true,
  stopPropagation = true,
}: SalePopupLinkProps) {
  if (!id) return <>{children}</>;
  const fromPath = from ?? "/";
  const href = `/sales?sale=${encodeURIComponent(id)}&from=${encodeURIComponent(fromPath)}`;
  return (
    <a
      href={href}
      onClick={(e) => {
        if (stopPropagation) e.stopPropagation();
        e.preventDefault();
        openInPopup(href);
        onAfterClick?.();
      }}
      className={cn(
        "cursor-pointer",
        defaultStyle &&
          "text-emerald-700 underline-offset-2 hover:underline dark:text-emerald-400",
        className,
      )}
    >
      {children}
    </a>
  );
}
