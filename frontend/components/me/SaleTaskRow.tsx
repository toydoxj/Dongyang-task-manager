"use client";

import { useMemo, useState } from "react";

import TaskKanban from "@/components/project/TaskKanban";
import type { Sale } from "@/lib/domain";
import { useTasks } from "@/lib/hooks";
import { cn } from "@/lib/utils";

import { filterCompletedByCutoff } from "@/app/me/_utils";

type CollapseCommand = {
  type: "expandTaskItems" | "collapseAll";
  version: number;
};

interface Props {
  sale: Sale;
  /** 영업 row 헤더 클릭 시 SalesEditModal 열기 — 부모가 setEditing 처리. */
  onClickHeader: (sale: Sale) => void;
  onChanged: () => void;
  /** 우리 앱 분류: 금주 TASK 활동 있으면 true (배지 표시 우선) */
  effectiveActive?: boolean;
  /** 영업별 task 추가 — ProjectTaskRow와 동일 패턴. 부모가 setTaskCreate({ saleId, status, category }) 처리. */
  onCreate?: (saleId: string, initialStatus?: string) => void;
  /** 상위 버튼의 마지막 접힘/펼침 명령. */
  collapseCommand: CollapseCommand;
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
  onCreate,
  collapseCommand,
}: Props) {
  // 영업 전체 task (sales_ids @> [sale.id]).
  const { data: saleTasksData } = useTasks({ sale_id: sale.id });
  // PR-FI/9: 완료 task 2주 cutoff (/me 4탭 동일 정책). 영업 상세는 SalesEditModal이
  // 자체 useTasks를 호출하므로 본 컴포넌트 한정 영향.
  const tasks = useMemo(
    () => filterCompletedByCutoff(saleTasksData?.items ?? []),
    [saleTasksData],
  );
  const displayStage =
    effectiveActive == null ? "" : effectiveActive ? "진행 중" : "대기";
  // 기본은 접힘. 상위 신호에 따라 TASK 보유 행 펼침/전체 접기를 동기화.
  const [collapseState, setCollapseState] = useState({
    commandVersion: collapseCommand.version,
    collapsed: true,
  });
  const collapsed =
    collapseState.commandVersion === collapseCommand.version
      ? collapseState.collapsed
      : collapseCommand.type === "collapseAll"
        ? true
        : tasks.length === 0;
  const syncCollapseState = (nextCollapsed: boolean): void =>
    setCollapseState({
      commandVersion: collapseCommand.version,
      collapsed: nextCollapsed,
    });
  const toggleCollapsed = (): void =>
    syncCollapseState(!collapsed);

  const expectedRevenue = sale.expected_revenue || 0;

  return (
    <section className="rounded-xl border border-emerald-200/70 bg-emerald-50/30 dark:border-emerald-900/40 dark:bg-emerald-950/20">
      {/* 펼침 막대 — ProjectTaskRow와 동일 패턴, 색만 emerald 계열 */}
      <div
        onClick={toggleCollapsed}
        role="button"
        tabIndex={0}
        aria-expanded={!collapsed}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            toggleCollapsed();
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
          <TaskKanban
            tasks={tasks}
            onChanged={onChanged}
            onCreate={
              onCreate
                ? (initialStatus) => onCreate(sale.id, initialStatus)
                : undefined
            }
          />
        </div>
      )}
    </section>
  );
}
