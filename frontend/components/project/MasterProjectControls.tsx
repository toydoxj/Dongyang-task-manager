"use client";

/**
 * MasterProjectModal 소형 sub-component 모음 — Input/NumInput/CheckBox/Tag/ValueRow.
 * PR-AW — MasterProjectModal.tsx에서 추출 (외과적 변경 / 동작 동일).
 *
 * 주의: `ValueRow`는 (label + value: string) descriptive 표시용으로,
 * project/_shared.tsx의 `Field`(label + children 입력 wrapper)와 다른 컴포넌트.
 */

import type React from "react";

import { cn } from "@/lib/utils";

export function Input({
  label,
  value,
  onChange,
  full,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  full?: boolean;
}) {
  return (
    <label className={cn("block text-xs", full && "sm:col-span-2")}>
      <span className="text-zinc-500">{label}</span>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-0.5 w-full rounded border border-zinc-300 bg-white px-2 py-1 text-xs text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
      />
    </label>
  );
}

export function NumInput({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number | null;
  onChange: (v: number | null) => void;
}) {
  return (
    <label className="block text-xs">
      <span className="text-zinc-500">{label}</span>
      <input
        type="number"
        value={value ?? ""}
        onChange={(e) => {
          const s = e.target.value;
          onChange(s === "" ? null : Number(s));
        }}
        className="mt-0.5 w-full rounded border border-zinc-300 bg-white px-2 py-1 text-xs text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
      />
    </label>
  );
}

export function CheckBox({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-1.5">
      <input
        type="checkbox"
        checked={value}
        onChange={(e) => onChange(e.target.checked)}
        className="h-3.5 w-3.5"
      />
      <span>{label}</span>
    </label>
  );
}

export function Tag({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "rounded-md border px-1.5 py-0.5 text-[10px] font-medium",
        className,
      )}
    >
      {children}
    </span>
  );
}

/** view 모드에서 (label + value) descriptive 표시. */
export function ValueRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-zinc-500">{label}</dt>
      <dd className="mt-0.5 text-zinc-800 dark:text-zinc-200">{value || "—"}</dd>
    </div>
  );
}
