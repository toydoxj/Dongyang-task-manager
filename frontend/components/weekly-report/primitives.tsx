"use client";

/**
 * 주간 업무일지 페이지 공유 primitives — Section 래퍼, 배지, 단순 표.
 * PR-AG — app/weekly-report/page.tsx에서 추출 (외과적 변경 / 동작 동일).
 */

import Link from "next/link";

import { useAuth } from "@/components/AuthGuard";

export type SectionBadge = "auto" | "manual" | "review";

export const BADGE_STYLE: Record<SectionBadge, string> = {
  auto: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  manual: "bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300",
  review: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
};
export const BADGE_LABEL: Record<SectionBadge, string> = {
  auto: "자동 집계",
  manual: "수동 입력",
  review: "검토 필요",
};

export function BadgeChip({ kind }: { kind: SectionBadge }) {
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-[9px] font-medium leading-none ${BADGE_STYLE[kind]}`}
    >
      {BADGE_LABEL[kind]}
    </span>
  );
}

export function Section({
  title,
  id,
  badge,
  sourceHref,
  children,
}: {
  title: string;
  id?: string;
  badge?: SectionBadge;
  /** WEEK-005 — admin이 이 섹션의 원본/관리 페이지로 점프할 link. admin만 노출. */
  sourceHref?: string;
  children: React.ReactNode;
}) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  // PDF 양식과 동일 — 회색 배경 + 좌측 회색 막대, 불릿 마크 없음.
  return (
    <section id={id} className="scroll-mt-16 space-y-2">
      <h2 className="flex items-center gap-1.5 border-l-[3px] border-zinc-500 bg-zinc-200/70 px-2 py-1 text-xs font-bold text-zinc-700 dark:border-zinc-500 dark:bg-zinc-800/70 dark:text-zinc-200">
        <span>{title}</span>
        {badge && <BadgeChip kind={badge} />}
        {sourceHref && isAdmin && (
          <Link
            href={sourceHref}
            className="ml-auto inline-flex items-center gap-1 rounded border border-zinc-400 bg-white px-1.5 py-0.5 text-[10px] font-medium text-zinc-600 hover:bg-zinc-100 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
            title="원본/관리 페이지"
          >
            관리 ↗
          </Link>
        )}
      </h2>
      {children}
    </section>
  );
}

export function BulletList({ items }: { items: string[] }) {
  return (
    <ul className="list-inside list-disc space-y-0.5 text-sm">
      {items.map((s, i) => (
        <li key={i}>{s}</li>
      ))}
    </ul>
  );
}

type CellValue = string | number | React.ReactNode;

export function SimpleTable({
  cols,
  rows,
  empty,
}: {
  cols: string[];
  rows: CellValue[][];
  empty?: string;
}) {
  if (rows.length === 0 && empty) {
    return (
      <div className="rounded border border-dashed border-zinc-300 px-3 py-2 text-center text-xs italic text-zinc-400 dark:border-zinc-700">
        {empty}
      </div>
    );
  }
  return (
    <div className="overflow-x-auto rounded border border-zinc-200 dark:border-zinc-800">
      <table className="w-full border-collapse text-xs">
        <thead className="bg-zinc-100 dark:bg-zinc-900">
          <tr>
            {cols.map((c) => (
              <th
                key={c}
                className="border-b border-zinc-200 px-2 py-1.5 text-left font-medium dark:border-zinc-800"
              >
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={i}
              className="border-b border-zinc-100 last:border-0 dark:border-zinc-800"
            >
              {row.map((cell, j) => (
                <td key={j} className="px-2 py-1 align-top">
                  {cell as React.ReactNode}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
