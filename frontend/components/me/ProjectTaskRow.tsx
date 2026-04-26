"use client";

import Link from "next/link";
import { useState } from "react";

import TaskKanban from "@/components/project/TaskKanban";
import { unassignMe } from "@/lib/api";
import type { Project, Task } from "@/lib/domain";
import { formatDate, formatPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

interface Props {
  project: Project;
  tasks: Task[];                       // 이 프로젝트의 task 만 (이미 필터됨)
  onChanged: () => void;               // task 변경 시 호출
  onCreate: (projectId: string, initialStatus?: string) => void;
  onUnassigned?: (projectId: string) => void;  // 담당 해제 후 호출 (즉시 제거 + revalidate)
  myName?: string;                     // 본인 이름 (담당 해제 표시 조건)
  /** 우리 앱 분류: 금주 TASK 활동 있으면 true (배지 표시 우선) */
  effectiveActive?: boolean;
}

const STAGE_BADGE: Record<string, string> = {
  "진행 중": "bg-blue-500/15 text-blue-400 border-blue-500/30",
  "대기": "bg-purple-500/15 text-purple-400 border-purple-500/30",
};

export default function ProjectTaskRow({
  project,
  tasks,
  onChanged,
  onCreate,
  onUnassigned,
  myName,
  effectiveActive,
}: Props) {
  // 우리 앱 분류 (effectiveActive) 가 우선, 없으면 노션 stage 사용
  const displayStage =
    effectiveActive == null
      ? project.stage
      : effectiveActive
        ? "진행 중"
        : "대기";
  const rate =
    typeof project.collection_rate === "number" ? project.collection_rate : null;
  const client =
    project.client_names.length > 0
      ? project.client_names.join(", ")
      : project.client_text;
  const [busy, setBusy] = useState(false);
  const isMine = !!myName && project.assignees.includes(myName);

  const handleUnassign = async (): Promise<void> => {
    if (!confirm(`"${project.name}" 프로젝트에서 본인 담당을 해제하시겠습니까?`))
      return;
    setBusy(true);
    try {
      await unassignMe(project.id);
      onUnassigned?.(project.id);
    } catch (err) {
      alert(err instanceof Error ? err.message : "담당 해제 실패");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-xl border border-zinc-200 bg-zinc-50/30 p-3 dark:border-zinc-800 dark:bg-zinc-950/30">
      {/* 프로젝트 헤더 */}
      <header className="mb-3 flex flex-wrap items-start justify-between gap-2 px-1">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <Link
              href={`/project?id=${project.id}`}
              className="truncate text-sm font-semibold text-zinc-900 hover:underline dark:text-zinc-100"
              title={project.name}
            >
              {project.name || "(제목 없음)"}
            </Link>
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
          </div>
          <p className="mt-0.5 text-[11px] text-zinc-500">
            <span className="font-mono">{project.code || "—"}</span>
            {client && <> · {client}</>}
            {project.contract_end && <> · 마감 {formatDate(project.contract_end)}</>}
            {rate != null && <> · 수금률 {formatPercent(rate)}</>}
          </p>
        </div>
        {isMine && (
          <button
            type="button"
            onClick={handleUnassign}
            disabled={busy}
            title="본인을 이 프로젝트 담당자에서 제거 (노션 이력 기록)"
            className="shrink-0 rounded-md border border-zinc-300 px-2 py-1 text-[10px] text-zinc-600 hover:border-red-400 hover:bg-red-500/5 hover:text-red-500 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-300"
          >
            {busy ? "해제중..." : "내 담당 해제"}
          </button>
        )}
      </header>

      {/* 이 프로젝트 단독 TaskKanban (별도 DndContext → 드래그 격리) */}
      <TaskKanban
        tasks={tasks}
        onChanged={onChanged}
        onCreate={(initialStatus) => onCreate(project.id, initialStatus)}
      />
    </section>
  );
}
