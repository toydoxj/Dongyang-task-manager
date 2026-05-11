"use client";

/**
 * /me 페이지 dumb sub-component 모음.
 * - ActivityBadge: 외근/출장/파견 표시
 * - TaskCard: TASK 카드 (제목/프로젝트/마감/상태 배지)
 * - ProjectTaskList: 프로젝트 카테고리 TASK 그리드
 * - CategoryCard: 카테고리별 TASK 카드
 *
 * PR-AL — app/me/page.tsx에서 추출 (외과적 변경 / 동작 동일).
 */

import Link from "next/link";

import type { Project, Task } from "@/lib/domain";
import { dDayLabel, formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

import { formatRange, statusBadgeColor } from "./_utils";

export function ActivityBadge({ activity }: { activity?: string }) {
  if (!activity || activity === "사무실") return null;
  const cls =
    activity === "외근"
      ? "bg-orange-500/15 text-orange-600 dark:text-orange-400"
      : activity === "출장"
        ? "bg-red-500/15 text-red-600 dark:text-red-400"
        : activity === "파견"
          ? "bg-violet-500/15 text-violet-600 dark:text-violet-400"
          : "bg-zinc-500/15 text-zinc-500";
  return (
    <span className={cn("rounded px-1 py-0.5 text-[9px] font-medium", cls)}>
      {activity}
    </span>
  );
}

export function TaskCard({
  task: t,
  project: proj,
  onClick,
  onDelete,
  warn,
}: {
  task: Task;
  project?: Project;
  onClick: () => void;
  onDelete?: () => void;
  warn?: boolean;
}) {
  return (
    <li
      className={cn(
        "group relative flex items-stretch overflow-hidden rounded-lg border bg-white dark:bg-zinc-900",
        warn
          ? "border-amber-300/60 dark:border-amber-700/60"
          : "border-zinc-200 dark:border-zinc-800",
      )}
    >
      {onDelete && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          className="absolute right-1 top-1 z-10 hidden rounded p-0.5 text-zinc-400 hover:bg-red-500/15 hover:text-red-500 group-hover:block"
          title="삭제"
        >
          ×
        </button>
      )}
      <button
        type="button"
        onClick={onClick}
        className="min-w-0 flex-1 px-3 py-2.5 text-left hover:bg-zinc-50 dark:hover:bg-zinc-800/50"
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium" title={t.title}>
              {t.title || "(제목 없음)"}
            </p>
            {proj && (
              <p
                className="mt-0.5 truncate text-[11px] text-zinc-600 dark:text-zinc-400"
                title={proj.name}
              >
                <span className="font-mono text-zinc-400">
                  {proj.code || proj.id.slice(0, 6)}
                </span>
                <span className="ml-1.5">{proj.name}</span>
              </p>
            )}
            <p className="mt-0.5 text-[11px] text-zinc-500">
              {t.status} · 마감 {formatDate(t.end_date)}
            </p>
          </div>
          <div className="flex shrink-0 flex-col items-end gap-1">
            <span
              className={cn(
                "rounded-md px-2 py-0.5 text-[10px] font-medium",
                statusBadgeColor(t),
              )}
            >
              {dDayLabel(t.end_date) || "—"}
            </span>
            <ActivityBadge activity={t.activity} />
          </div>
        </div>
      </button>
      {t.project_ids[0] && (
        <Link
          href={`/projects/${t.project_ids[0]}`}
          className="flex shrink-0 items-center px-3 text-[10px] text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800"
          title="프로젝트로 이동"
        >
          →
        </Link>
      )}
    </li>
  );
}

export function ProjectTaskList({
  items,
  findProject,
  onClickTask,
  onDeleteTask,
}: {
  items: Task[];
  findProject: (pid: string | undefined) => Project | undefined;
  onClickTask: (t: Task) => void;
  onDeleteTask: (t: Task) => void;
}) {
  return (
    <div>
      <h3 className="mb-1.5 flex items-center gap-2 text-xs font-medium text-zinc-600 dark:text-zinc-400">
        <span>프로젝트</span>
        <span className="text-zinc-400">({items.length})</span>
      </h3>
      <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {items.map((t) => (
          <TaskCard
            key={t.id}
            task={t}
            project={findProject(t.project_ids[0])}
            onClick={() => onClickTask(t)}
            onDelete={() => onDeleteTask(t)}
          />
        ))}
      </ul>
    </div>
  );
}

export function CategoryCard({
  label,
  items,
  onClickTask,
  showCategoryBadge,
  showTime,
  showProjectBadge,
  findProject,
  onAdd,
  addLabel,
}: {
  label: string;
  items: Task[];
  onClickTask: (t: Task) => void;
  showCategoryBadge?: boolean;
  showTime?: boolean;
  showProjectBadge?: boolean;
  findProject?: (pid: string | undefined) => Project | undefined;
  /** 우상단 + 버튼 클릭 핸들러. 없으면 버튼 미표시. */
  onAdd?: () => void;
  /** + 버튼 라벨. 기본 '+ 새 항목'. */
  addLabel?: string;
}) {
  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900">
      <header className="mb-2 flex items-center justify-between gap-2">
        <h4 className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">
          {label}
        </h4>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-zinc-500">{items.length}</span>
          {onAdd && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onAdd();
              }}
              className="rounded-md border border-zinc-300 px-1.5 py-0.5 text-[10px] hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
              title={addLabel ?? "+ 새 항목"}
            >
              {addLabel ?? "+"}
            </button>
          )}
        </div>
      </header>
      {items.length === 0 ? (
        <p className="py-4 text-center text-[11px] text-zinc-400">없음</p>
      ) : (
        <ul className="space-y-1.5">
          {items.map((t) => (
            <li key={t.id}>
              <button
                type="button"
                onClick={() => onClickTask(t)}
                className="block w-full rounded-md border border-zinc-200 bg-white px-2 py-1.5 text-left text-xs hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950 dark:hover:bg-zinc-900"
              >
                <p className="truncate font-medium" title={t.title}>
                  {t.title || "(제목 없음)"}
                </p>
                {showProjectBadge && t.category === "프로젝트" && findProject && (
                  <p className="mt-0.5 truncate text-[10px] text-zinc-500">
                    {(() => {
                      const proj = findProject(t.project_ids[0]);
                      return proj ? `${proj.code || ""} ${proj.name}` : "프로젝트";
                    })()}
                  </p>
                )}
                <p className="mt-0.5 flex items-center justify-between gap-1 text-[10px] text-zinc-500">
                  <span className="truncate">
                    {showTime
                      ? formatRange(t.start_date, t.end_date)
                      : `마감 ${formatDate(t.end_date)}`}
                  </span>
                  <span className="flex shrink-0 items-center gap-1">
                    <ActivityBadge activity={t.activity} />
                    {showCategoryBadge && t.category && (
                      <span className="rounded bg-zinc-100 px-1 py-0.5 text-[9px] text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                        {t.category}
                      </span>
                    )}
                    {!showCategoryBadge && (
                      <span
                        className={cn(
                          "rounded px-1 py-0.5 text-[9px] font-medium",
                          statusBadgeColor(t),
                        )}
                      >
                        {dDayLabel(t.end_date) || "—"}
                      </span>
                    )}
                  </span>
                </p>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
