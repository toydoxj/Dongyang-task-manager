"use client";

import { useState } from "react";

import TaskKanban from "@/components/project/TaskKanban";
import type { Sale } from "@/lib/domain";
import { useTasks } from "@/lib/hooks";
import { cn } from "@/lib/utils";

interface Props {
  sale: Sale;
  /** 영업 row 헤더 클릭 시 SalesEditModal 열기 — 부모가 setEditing 처리. */
  onClickHeader: (sale: Sale) => void;
  onChanged: () => void;
  /** 우리 앱 분류: 금주 TASK 활동 있으면 true (배지 표시 우선) */
  effectiveActive?: boolean;
}

const STAGE_BADGE: Record<string, string> = {
  "진행 중": "bg-blue-500/15 text-blue-400 border-blue-500/30",
  "대기": "bg-purple-500/15 text-purple-400 border-purple-500/30",
};

export default function SaleTaskRow({
  sale,
  onClickHeader,
  onChanged,
  effectiveActive,
}: Props) {
  // 영업 전체 task (sales_ids @> [sale.id]).
  const { data: saleTasksData } = useTasks({ sale_id: sale.id });
  const tasks = saleTasksData?.items ?? [];
  const displayStage =
    effectiveActive == null ? "" : effectiveActive ? "진행 중" : "대기";
  const [collapsed, setCollapsed] = useState(true);

  const expectedRevenue = sale.expected_revenue || 0;

  return (
    <section className="rounded-xl border border-emerald-200/70 bg-emerald-50/30 dark:border-emerald-900/40 dark:bg-emerald-950/20">
      {/* 펼침 막대 — ProjectTaskRow와 동일 패턴, 색만 emerald 계열 */}
      <div
        onClick={() => setCollapsed((v) => !v)}
        role="button"
        tabIndex={0}
        aria-expanded={!collapsed}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setCollapsed((v) => !v);
          }
        }}
        className="flex w-full cursor-pointer items-start gap-2 px-3 py-2 hover:bg-emerald-100/40 dark:hover:bg-emerald-900/20"
      >
        <span className="mt-0.5 shrink-0 text-zinc-400">
          {collapsed ? "▶" : "▼"}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onClickHeader(sale);
              }}
              className="truncate text-left text-sm font-semibold text-emerald-900 hover:underline dark:text-emerald-100"
              title={sale.name}
            >
              {sale.name || "(영업명 없음)"}
            </button>
            {sale.is_bid && (
              <span className="shrink-0 rounded border border-blue-500/30 bg-blue-500/10 px-1.5 py-0.5 text-[10px] font-medium text-blue-700 dark:text-blue-300">
                입찰
              </span>
            )}
            {displayStage && (
              <span
                className={cn(
                  "shrink-0 rounded-md border px-1.5 py-0.5 text-[10px] font-medium",
                  STAGE_BADGE[displayStage] ??
                    "border-zinc-500/30 bg-zinc-500/15 text-zinc-400",
                )}
              >
                {displayStage}
              </span>
            )}
            <span className="shrink-0 text-[10px] text-zinc-500">
              TASK {tasks.length}건
            </span>
          </div>
          <p className="mt-0.5 text-[11px] text-zinc-500">
            <span className="font-mono">{sale.code || "—"}</span>
            {sale.kind && <> · {sale.kind}</>}
            {sale.stage && <> · {sale.stage}</>}
            {sale.estimated_amount != null && sale.estimated_amount > 0 && (
              <> · 견적 {sale.estimated_amount.toLocaleString("ko-KR")}원</>
            )}
            {sale.probability != null && sale.probability > 0 && (
              <> · 수주확률 {Math.round(sale.probability)}%</>
            )}
            {expectedRevenue > 0 && (
              <span className="ml-1 text-emerald-700 dark:text-emerald-400">
                (기대 {expectedRevenue.toLocaleString("ko-KR")}원)
              </span>
            )}
          </p>
        </div>
      </div>

      {!collapsed && (
        <div className="border-t border-emerald-200/70 p-3 dark:border-emerald-900/40">
          {/* 새 task 생성은 영업 모달(SalesEditModal)에서 — onCreate 미전달 */}
          <TaskKanban tasks={tasks} onChanged={onChanged} />
        </div>
      )}
    </section>
  );
}
