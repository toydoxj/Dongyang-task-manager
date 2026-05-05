"use client";

import type { Sale } from "@/lib/domain";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

interface Props {
  sales: Sale[];
  onClickRow: (sale: Sale) => void;
  /** kind/stage 모두 표시할지 — /me의 sub-section처럼 kind 필터된 상태에서는 false */
  showKindColumn?: boolean;
}

const KRW = (n: number | null | undefined): string => {
  if (n == null) return "";
  return n.toLocaleString("ko-KR") + "원";
};

const KRW_SHORT = (n: number): string => {
  if (n >= 100_000_000) return `${(n / 100_000_000).toFixed(1)}억`;
  if (n >= 10_000_000) return `${(n / 10_000_000).toFixed(1)}천만`;
  if (n >= 10_000) return `${(n / 10_000).toFixed(0)}만`;
  return n.toLocaleString("ko-KR");
};

const stageBadgeColor = (stage: string): string => {
  switch (stage) {
    case "완료":
      return "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400";
    case "제출":
      return "bg-blue-500/15 text-blue-700 dark:text-blue-400";
    case "진행":
      return "bg-orange-500/15 text-orange-700 dark:text-orange-400";
    case "준비":
      return "bg-yellow-500/15 text-yellow-700 dark:text-yellow-400";
    case "종결":
      return "bg-zinc-300/30 text-zinc-500";
    default:
      return "bg-purple-500/15 text-purple-700 dark:text-purple-400";
  }
};

export default function SalesTable({
  sales,
  onClickRow,
  showKindColumn = true,
}: Props) {
  if (sales.length === 0) {
    return (
      <p className="rounded-md border border-zinc-200 bg-white p-4 text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900">
        영업 건이 없습니다.
      </p>
    );
  }

  const totalExpected = sales.reduce((s, x) => s + (x.expected_revenue || 0), 0);

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[860px] text-sm">
        <thead>
          <tr className="border-b border-zinc-200 text-left text-[11px] uppercase text-zinc-500 dark:border-zinc-800">
            <th className="px-2 py-2">견적서명</th>
            {showKindColumn && <th className="px-2 py-2">유형</th>}
            <th className="px-2 py-2">단계</th>
            <th className="px-2 py-2 text-right">견적금액</th>
            <th className="px-2 py-2 text-right">기대매출</th>
            <th className="px-2 py-2">담당</th>
            <th className="px-2 py-2">제출일</th>
          </tr>
        </thead>
        <tbody>
          {sales.map((s) => (
            <tr
              key={s.id}
              className="cursor-pointer border-b border-zinc-100 hover:bg-zinc-50 dark:border-zinc-900 dark:hover:bg-zinc-800/50"
              onClick={() => onClickRow(s)}
            >
              <td className="px-2 py-2">
                <div className="font-medium">{s.name || "(이름 없음)"}</div>
                {s.category.length > 0 && (
                  <div className="mt-0.5 text-[10px] text-zinc-500">
                    {s.category.join(" · ")}
                  </div>
                )}
              </td>
              {showKindColumn && (
                <td className="px-2 py-2 text-xs">
                  <span
                    className={cn(
                      "rounded px-1.5 py-0.5 text-[10px]",
                      s.kind === "기술지원"
                        ? "bg-purple-500/15 text-purple-700 dark:text-purple-400"
                        : "bg-blue-500/15 text-blue-700 dark:text-blue-400",
                    )}
                  >
                    {s.kind || "—"}
                  </span>
                </td>
              )}
              <td className="px-2 py-2 text-xs">
                <span
                  className={cn(
                    "rounded px-1.5 py-0.5 text-[10px]",
                    stageBadgeColor(s.stage),
                  )}
                >
                  {s.stage || "—"}
                </span>
              </td>
              <td className="px-2 py-2 text-right font-mono text-xs">
                {s.estimated_amount != null ? KRW(s.estimated_amount) : "—"}
              </td>
              <td className="px-2 py-2 text-right font-mono text-xs text-emerald-700 dark:text-emerald-400">
                {s.expected_revenue > 0 ? KRW_SHORT(s.expected_revenue) : "—"}
              </td>
              <td className="px-2 py-2 text-xs text-zinc-600 dark:text-zinc-400">
                {s.assignees.join(", ") || "—"}
              </td>
              <td className="px-2 py-2 text-xs text-zinc-500">
                {s.submission_date ? formatDate(s.submission_date) : "—"}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t border-zinc-200 dark:border-zinc-800">
            <td
              colSpan={showKindColumn ? 4 : 3}
              className="px-2 py-2 text-right text-xs font-medium text-zinc-600 dark:text-zinc-400"
            >
              기대매출 합계
            </td>
            <td className="px-2 py-2 text-right font-mono text-sm font-semibold text-emerald-700 dark:text-emerald-400">
              {KRW(totalExpected)}
            </td>
            <td colSpan={2} />
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
