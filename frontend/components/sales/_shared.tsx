"use client";

/**
 * SalesEditModal / QuoteForm 등 sales sub-component 공유 UI 헬퍼.
 * - inputCls: 공통 input className (disabled 스타일 포함)
 * - Field: label + children 래퍼
 * - TabButton: 탭 버튼
 * - Section: 견적서 폼 섹션 wrapper
 *
 * PR-AE — SalesEditModal.tsx에서 추출.
 * PR-AN — QuoteForm.tsx에서 Section 추가 + inputCls disabled 스타일 통합.
 */

import type React from "react";

export const inputCls =
  "w-full rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm focus:border-zinc-500 focus:outline-none disabled:bg-zinc-100 disabled:text-zinc-500 disabled:border-zinc-200 disabled:cursor-not-allowed dark:border-zinc-700 dark:bg-zinc-900 dark:disabled:bg-zinc-800/50 dark:disabled:text-zinc-500";

export function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <label className="block text-[11px] font-medium text-zinc-600 dark:text-zinc-400">
        {label}
      </label>
      {children}
    </div>
  );
}

export function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        active
          ? "border-b-2 border-zinc-900 px-4 py-2 text-sm font-medium text-zinc-900 dark:border-zinc-100 dark:text-zinc-100"
          : "px-4 py-2 text-sm text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-300"
      }
    >
      {children}
    </button>
  );
}

export function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2 rounded-md border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900">
      <h4 className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
        {title}
      </h4>
      {children}
    </div>
  );
}
