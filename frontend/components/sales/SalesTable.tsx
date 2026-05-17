"use client";

import { useMemo } from "react";

import { BID_STAGES, type Sale } from "@/lib/domain";
import { formatDate } from "@/lib/format";
import { useClients } from "@/lib/hooks";
import { cn } from "@/lib/utils";

/** PR-FC: 정렬 가능 컬럼 7개 (사용자 결정 — 핵심 6 + 담당).
 * PR-FD: CODE 추가 — natural sort (영25-9 < 영25-10). */
export type SalesSortKey =
  | "code"
  | "stage"
  | "estimated_amount"
  | "probability"
  | "expected_revenue"
  | "submission_date"
  | "client"
  | "assignees";
export type SortDir = "asc" | "desc";

interface Props {
  sales: Sale[];
  onClickRow: (sale: Sale) => void;
  /** kind/stage 모두 표시할지 — /me의 sub-section처럼 kind 필터된 상태에서는 false */
  showKindColumn?: boolean;
  /** 정렬 상태. 외부에서 관리 — header click이 onSortChange로 위임. */
  sortKey?: SalesSortKey | null;
  sortDir?: SortDir;
  onSortChange?: (key: SalesSortKey) => void;
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

/** 정렬 가능 header. 정렬 안 됨이면 회색 ⇅, asc=▲, desc=▼. */
function SortableTh({
  k,
  label,
  align = "left",
  sortKey,
  sortDir,
  onSortChange,
}: {
  k: SalesSortKey;
  label: string;
  align?: "left" | "right";
  sortKey?: SalesSortKey | null;
  sortDir?: SortDir;
  onSortChange?: (k: SalesSortKey) => void;
}): React.ReactElement {
  const active = sortKey === k;
  const arrow = active ? (sortDir === "asc" ? "▲" : "▼") : "⇅";
  return (
    <th
      className={cn(
        "select-none px-2 py-2",
        align === "right" && "text-right",
        onSortChange && "cursor-pointer hover:text-zinc-700 dark:hover:text-zinc-200",
      )}
      onClick={onSortChange ? () => onSortChange(k) : undefined}
    >
      {label}
      <span className={cn("ml-1 text-[9px]", !active && "text-zinc-300 dark:text-zinc-600")}>
        {arrow}
      </span>
    </th>
  );
}

export default function SalesTable({
  sales,
  onClickRow,
  showKindColumn = true,
  sortKey = null,
  sortDir = "desc",
  onSortChange,
}: Props) {
  // client_id → 발주처 이름 lookup. useClients()가 자체 cache를 가지므로 추가 비용 없음.
  const { data: clientsData } = useClients(true);
  const clientNameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const c of clientsData?.items ?? []) map.set(c.id, c.name);
    return map;
  }, [clientsData]);

  // PR-FC: client-side 정렬. sortKey 미지정이면 backend 정렬 순서(created_time DESC) 유지.
  const sorted = useMemo(() => {
    if (!sortKey) return sales;
    const dir = sortDir === "asc" ? 1 : -1;
    const stageOrder = (s: string): number => {
      const i = (BID_STAGES as readonly string[]).indexOf(s);
      return i === -1 ? BID_STAGES.length : i;
    };
    // PR-FD: 영업코드 natural sort — 영{YY}-{NNN} / {YY}-영업-{NNN} 둘 다
    // 처리. 마지막 숫자 chunk를 분리해 prefix(string) + tail(number)로 비교.
    // padding 0 일관성 무관 (5 vs 10 정확 비교).
    const codeKey = (c: string): [string, number] => {
      const m = c.match(/(\d+)$/);
      if (!m) return [c, Number.POSITIVE_INFINITY];
      return [c.slice(0, m.index), parseInt(m[1], 10)];
    };
    const cmp = (a: Sale, b: Sale): number => {
      switch (sortKey) {
        case "code": {
          // 빈 code는 항상 맨 뒤 (asc/desc 무관)
          if (!a.code && !b.code) return 0;
          if (!a.code) return 1;
          if (!b.code) return -1;
          const [ap, an] = codeKey(a.code);
          const [bp, bn] = codeKey(b.code);
          const px = ap.localeCompare(bp, "ko");
          if (px !== 0) return px * dir;
          return (an - bn) * dir;
        }
        case "stage":
          return (stageOrder(a.stage) - stageOrder(b.stage)) * dir;
        case "estimated_amount":
          return (
            ((a.estimated_amount ?? -Infinity) -
              (b.estimated_amount ?? -Infinity)) *
            dir
          );
        case "probability":
          return ((a.probability ?? -Infinity) - (b.probability ?? -Infinity)) * dir;
        case "expected_revenue":
          return ((a.expected_revenue || 0) - (b.expected_revenue || 0)) * dir;
        case "submission_date": {
          // null은 항상 맨 뒤 (asc/desc 무관)
          if (!a.submission_date && !b.submission_date) return 0;
          if (!a.submission_date) return 1;
          if (!b.submission_date) return -1;
          return a.submission_date.localeCompare(b.submission_date) * dir;
        }
        case "client": {
          const an = a.client_id ? clientNameById.get(a.client_id) ?? "" : "";
          const bn = b.client_id ? clientNameById.get(b.client_id) ?? "" : "";
          return an.localeCompare(bn, "ko") * dir;
        }
        case "assignees": {
          const an = a.assignees.join(",");
          const bn = b.assignees.join(",");
          return an.localeCompare(bn, "ko") * dir;
        }
      }
    };
    return [...sales].sort(cmp);
  }, [sales, sortKey, sortDir, clientNameById]);

  if (sales.length === 0) {
    return (
      <p className="rounded-md border border-zinc-200 bg-white p-4 text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900">
        영업 건이 없습니다.
      </p>
    );
  }

  const totalExpected = sales.reduce((s, x) => s + (x.expected_revenue || 0), 0);

  const thSort = { sortKey, sortDir, onSortChange };

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[920px] text-sm">
        <thead>
          <tr className="border-b border-zinc-200 text-left text-[11px] uppercase text-zinc-500 dark:border-zinc-800">
            <SortableTh k="code" label="CODE" {...thSort} />
            <th className="px-2 py-2">용역명</th>
            <SortableTh k="client" label="발주처" {...thSort} />
            {showKindColumn && <th className="px-2 py-2">유형</th>}
            <SortableTh k="stage" label="단계" {...thSort} />
            <SortableTh k="estimated_amount" label="견적금액" align="right" {...thSort} />
            <SortableTh k="probability" label="확률" align="right" {...thSort} />
            <SortableTh k="expected_revenue" label="기대매출" align="right" {...thSort} />
            <SortableTh k="assignees" label="담당" {...thSort} />
            <SortableTh k="submission_date" label="제출일" {...thSort} />
          </tr>
        </thead>
        <tbody>
          {sorted.map((s) => (
            <tr
              key={s.id}
              className="cursor-pointer border-b border-zinc-100 hover:bg-zinc-50 dark:border-zinc-900 dark:hover:bg-zinc-800/50"
              onClick={() => onClickRow(s)}
            >
              <td className="px-2 py-2 font-mono text-[11px] text-zinc-500">
                {s.code || "—"}
              </td>
              <td className="px-2 py-2">
                <div className="font-medium">{s.name || "(이름 없음)"}</div>
                {s.category.length > 0 && (
                  <div className="mt-0.5 text-[10px] text-zinc-500">
                    {s.category.join(" · ")}
                  </div>
                )}
              </td>
              <td className="px-2 py-2 text-xs text-zinc-700 dark:text-zinc-300">
                {s.client_id ? clientNameById.get(s.client_id) || "—" : "—"}
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
              <td className="px-2 py-2 text-right font-mono text-xs">
                {s.probability != null ? `${s.probability}%` : "—"}
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
              colSpan={showKindColumn ? 7 : 6}
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
