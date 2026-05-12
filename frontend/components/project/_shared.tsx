"use client";

/**
 * project/* 모달·편집 컴포넌트 공유 UI 헬퍼.
 * - inputCls: 공통 input className
 * - Field: label + children 래퍼 (required 옵션 포함)
 *
 * PR-AU — TaskEditModal/ProjectEditModal/SealRequestCreateModal/
 * SealRequestEditModal/ProjectStageChangeModal 5+ 파일에서 중복 정의 통합.
 */

import type React from "react";

export const inputCls =
  "w-full rounded-md border border-zinc-300 bg-white px-2.5 py-1.5 text-sm outline-none focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-950";

export function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-zinc-500">
        {label}
        {required && <span className="ml-1 text-red-500">*</span>}
      </span>
      {children}
    </label>
  );
}
