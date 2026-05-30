"use client";

import { ProjectPopupLink } from "@/components/common/PopupLinks";
import { useMemo, useState } from "react";

import TaskKanban from "@/components/project/TaskKanban";
import { unassignMe } from "@/lib/api";
import type { Project } from "@/lib/domain";
import { formatDate, formatPercent } from "@/lib/format";
import { useTasks } from "@/lib/hooks";

import { filterCompletedByCutoff } from "@/app/me/_utils";
import { cn } from "@/lib/utils";

type CollapseCommand = {
  type: "expandTaskItems" | "collapseAll";
  version: number;
};

interface Props {
  project: Project;
  onChanged: () => void;               // task 변경 시 호출
  onCreate: (projectId: string, initialStatus?: string) => void;
  onUnassigned?: (projectId: string) => void;  // 담당 해제 후 호출 (즉시 제거 + revalidate)
  myName?: string;                     // 본인 이름 (담당 해제 표시 조건)
  /** admin/team_lead 가 다른 직원 페이지를 볼 때 — 그 직원 명의로 unassign */
  forUser?: string;
  /** 우리 앱 분류: 금주 TASK 활동 있으면 true (배지 표시 우선) */
  effectiveActive?: boolean;
  /** 상위 버튼의 마지막 접힘/펼침 명령. */
  collapseCommand: CollapseCommand;
}

const STAGE_BADGE: Record<string, string> = {
  "진행 중": "bg-blue-500/15 text-blue-400 border-blue-500/30",
  "대기": "bg-purple-500/15 text-purple-400 border-purple-500/30",
};

export default function ProjectTaskRow({
  project,
  onChanged,
  onCreate,
  onUnassigned,
  myName,
  forUser,
  effectiveActive,
  collapseCommand,
}: Props) {
  // 프로젝트 전체 task (다른 직원 담당분 포함) — 카운트 + 칸반에 사용.
  // 페이지 레벨 mine tasks 는 '해야할 일' 과 진행중/대기 분류에만 쓰이고
  // 여기 칸반에는 본인/타인 가리지 않고 모두 노출.
  const { data: projectTasksData } = useTasks({ project_id: project.id });
  // PR-FI/9: 완료 task 2주 cutoff (page.tsx의 mine tasks와 동일 정책).
  const tasks = useMemo(
    () => filterCompletedByCutoff(projectTasksData?.items ?? []),
    [projectTasksData],
  );
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
  const isMine = !!myName && project.assignees.includes(myName);

  const handleUnassign = async (): Promise<void> => {
    const subject = forUser ? `${forUser} 님` : "본인";
    if (
      !confirm(
        `"${project.name}" 프로젝트에서 ${subject} 담당을 해제하시겠습니까?`,
      )
    )
      return;
    setBusy(true);
    try {
      await unassignMe(project.id, { forUser });
      onUnassigned?.(project.id);
    } catch (err) {
      alert(err instanceof Error ? err.message : "담당 해제 실패");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-xl border border-zinc-200 bg-zinc-50/30 dark:border-zinc-800 dark:bg-zinc-950/30">
      {/* 펼침 막대 — 빈 공간 클릭 시 TASK 노출. 내부 링크/버튼은 stopPropagation */}
      <div
        onClick={() => toggleCollapsed()}
        role="button"
        tabIndex={0}
        aria-expanded={!collapsed}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            toggleCollapsed();
          }
        }}
        className="flex w-full cursor-pointer items-start gap-2 px-3 py-2 hover:bg-zinc-100/40 dark:hover:bg-zinc-800/30"
      >
        <span className="mt-0.5 shrink-0 text-zinc-400">
          {collapsed ? "▶" : "▼"}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <ProjectPopupLink
              id={project.id}
              defaultStyle={false}
              className="truncate text-sm font-semibold text-zinc-900 hover:underline dark:text-zinc-100"
            >
              {project.name || "(제목 없음)"}
            </ProjectPopupLink>
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
            <span className="font-mono">{project.code || "—"}</span>
            {client && <> · {client}</>}
            {project.contract_end && <> · 마감 {formatDate(project.contract_end)}</>}
            {rate != null && <> · 수금률 {formatPercent(rate)}</>}
          </p>
        </div>
        {isMine && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              void handleUnassign();
            }}
            disabled={busy}
            title="본인을 이 프로젝트 담당자에서 제거"
            className="shrink-0 rounded-md border border-zinc-300 px-2 py-1 text-[10px] text-zinc-600 hover:border-red-400 hover:bg-red-500/5 hover:text-red-500 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-300"
          >
            {busy ? "해제중..." : "내 담당 해제"}
          </button>
        )}
      </div>

      {/* 펼침 시: 이 프로젝트 단독 TaskKanban (별도 DndContext → 드래그 격리) */}
      {!collapsed && (
        <div className="border-t border-zinc-200 p-3 dark:border-zinc-800">
          <TaskKanban
            tasks={tasks}
            onChanged={onChanged}
            onCreate={(initialStatus) => onCreate(project.id, initialStatus)}
          />
        </div>
      )}
    </section>
  );
}
