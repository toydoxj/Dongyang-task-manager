"use client";

/**
 * SalesEditModal 및 관련 sales sub-component 공유 UI 헬퍼.
 * - inputCls: 공통 input className
 * - Field: label + children 래퍼
 * - TabButton: 탭 버튼
 *
 * PR-AE — SalesEditModal.tsx에서 추출 (외과적 변경 / 동작 동일).
 */

import type React from "react";

export const inputCls =
  "w-full rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900";

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
