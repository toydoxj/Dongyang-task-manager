"use client";

/**
 * StageBoard 칸반 column·card sub-components.
 * PR-BA — components/dashboard/StageBoard.tsx에서 추출 (외과적 변경 / 동작 동일).
 */

import { useDraggable, useDroppable } from "@dnd-kit/core";
import Link from "next/link";
import { useState } from "react";

import type { Project } from "@/lib/domain";
import { formatWon } from "@/lib/format";
import { cn } from "@/lib/utils";

export type CloseMode = "완료" | "타절" | "종결";

export const STAGE_COLOR: Record<string, string> = {
  "진행중": "border-blue-500/40 bg-blue-500/5",
  "대기": "border-purple-500/40 bg-purple-500/5",
  "보류": "border-pink-500/40 bg-pink-500/5",
  "완료": "border-emerald-500/40 bg-emerald-500/5",
  "타절": "border-red-500/40 bg-red-500/5",
  "종결": "border-zinc-500/40 bg-zinc-500/5",
  "이관": "border-zinc-400/30 bg-zinc-400/5",
};

export const STAGE_DOT: Record<string, string> = {
  "진행중": "bg-blue-500",
  "대기": "bg-purple-500",
  "보류": "bg-pink-500",
  "완료": "bg-emerald-500",
  "타절": "bg-red-500",
  "종결": "bg-zinc-500",
  "이관": "bg-zinc-400",
};

export function ClosedStackColumn({
  sections,
  draggable,
}: {
  sections: { stage: string; items: Project[] }[];
  draggable: boolean;
}) {
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-2">
      {sections.map((s) => (
        <ClosedSubSection
          key={s.stage}
          stage={s.stage}
          items={s.items}
          draggable={draggable}
        />
      ))}
    </div>
  );
}

export function ClosedSubSection({
  stage,
  items,
  draggable,
}: {
  stage: string;
  items: Project[];
  draggable: boolean;
}) {
  const { isOver, setNodeRef } = useDroppable({
    id: stage,
    disabled: !draggable,
  });
  const total = items.reduce((s, p) => s + (p.contract_amount ?? 0), 0);

  return (
    <div
      ref={setNodeRef}
      className={cn(
        "flex flex-col rounded-xl border bg-white transition-colors dark:bg-zinc-900",
        STAGE_COLOR[stage] ?? "border-zinc-300",
        isOver && "ring-2 ring-blue-400",
      )}
    >
      <header className="flex items-center justify-between border-b border-zinc-200 px-3 py-1.5 dark:border-zinc-800">
        <div className="flex items-center gap-1.5">
          <span className={cn("h-2 w-2 rounded-full", STAGE_DOT[stage])} />
          <h3 className="text-xs font-semibold">{stage}</h3>
          <span className="text-[10px] text-zinc-500">{items.length}건</span>
        </div>
        <span className="text-[10px] font-medium text-zinc-600 dark:text-zinc-400">
          {formatWon(total, true)}
        </span>
      </header>
      <ul className="max-h-[140px] space-y-1 overflow-y-auto p-1.5">
        {items.length === 0 && (
          <li className="px-2 py-3 text-center text-[10px] text-zinc-400">
            비어있음
          </li>
        )}
        {items.map((p) => (
          <ProjectCard key={p.id} project={p} draggable={draggable} />
        ))}
      </ul>
    </div>
  );
}

export function CreateColumn({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-32 flex-shrink-0 flex-col items-center justify-center rounded-xl border border-dashed border-zinc-300 bg-zinc-50/40 text-xs text-zinc-500 transition-colors hover:border-zinc-400 hover:bg-zinc-100 hover:text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900/40 dark:hover:border-zinc-600 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
      title="새 프로젝트 생성 (담당자 비어있음 — 진행단계 '대기'로 시작)"
    >
      <span className="text-2xl leading-none">+</span>
      <span className="mt-1">새 프로젝트</span>
    </button>
  );
}

export function StageColumn({
  stage,
  items,
  draggable,
}: {
  stage: string;
  items: Project[];
  draggable: boolean;
}) {
  const isAutoStage = stage === "진행중";
  const { isOver, setNodeRef } = useDroppable({
    id: stage,
    disabled: isAutoStage || !draggable, // 진행중 컬럼/비-admin은 drop 차단
  });
  const total = items.reduce((s, p) => s + (p.contract_amount ?? 0), 0);
  const [expanded, setExpanded] = useState(false);
  const VISIBLE = 50;
  const visibleItems = expanded ? items : items.slice(0, VISIBLE);

  return (
    <div
      ref={setNodeRef}
      className={cn(
        "flex min-w-0 flex-1 flex-col rounded-xl border bg-white transition-colors dark:bg-zinc-900",
        STAGE_COLOR[stage] ?? "border-zinc-300",
        isOver && !isAutoStage && "ring-2 ring-blue-400",
        isAutoStage && "opacity-95",
      )}
    >
      <header className="flex items-center justify-between border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
        <div className="flex items-center gap-2">
          <span className={cn("h-2 w-2 rounded-full", STAGE_DOT[stage])} />
          <h3 className="text-sm font-semibold">{stage}</h3>
          <span className="text-xs text-zinc-500">{items.length}건</span>
          {isAutoStage && (
            <span
              className="rounded bg-blue-500/15 px-1 py-0.5 text-[9px] text-blue-500"
              title="금주 TASK 활동으로 자동 결정"
            >
              자동
            </span>
          )}
        </div>
        <span className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
          {formatWon(total, true)}
        </span>
      </header>

      <ul className="max-h-[480px] space-y-1.5 overflow-y-auto p-2">
        {items.length === 0 && (
          <li className="px-2 py-6 text-center text-xs text-zinc-400">
            비어있음
          </li>
        )}
        {visibleItems.map((p) => (
          <ProjectCard key={p.id} project={p} draggable={draggable} />
        ))}
        {items.length > VISIBLE && (
          <li>
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="w-full rounded-md py-1.5 text-center text-[10px] text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-300"
            >
              {expanded
                ? "▲ 접기"
                : `▼ ${items.length - VISIBLE}건 더 보기`}
            </button>
          </li>
        )}
      </ul>
    </div>
  );
}

export function ProjectCard({
  project: p,
  draggable,
}: {
  project: Project;
  draggable: boolean;
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } =
    useDraggable({ id: p.id, disabled: !draggable });

  const style: React.CSSProperties | undefined = transform
    ? {
        transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`,
        zIndex: 50,
      }
    : undefined;

  return (
    <li
      ref={setNodeRef}
      style={style}
      className={cn(
        "select-none touch-none",
        isDragging && "opacity-60",
      )}
      {...attributes}
      {...listeners}
    >
      <div className="rounded-md border border-zinc-200 bg-white p-2.5 text-xs transition-colors hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950 dark:hover:bg-zinc-900">
        <div className="flex items-start justify-between gap-1">
          <p
            className="truncate font-medium text-zinc-900 dark:text-zinc-100"
            title={p.name}
          >
            {p.name || "(제목 없음)"}
          </p>
          {/* 카드 자체는 drag 영역. 우측 → 링크는 drag 충돌 방지 위해 PointerEvents 막음 */}
          <Link
            href={`/projects/${p.id}`}
            onPointerDown={(e) => e.stopPropagation()}
            className="shrink-0 text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200"
            title="상세"
          >
            ↗
          </Link>
        </div>
        <div className="mt-1 flex items-center justify-between">
          <span className="font-mono text-[10px] text-zinc-500">
            {p.code || "—"}
          </span>
          <span className="text-[10px] text-zinc-500">
            {p.assignees.length > 0
              ? p.assignees.length === 1
                ? p.assignees[0]
                : `${p.assignees[0]} +${p.assignees.length - 1}`
              : "—"}
          </span>
        </div>
      </div>
    </li>
  );
}
