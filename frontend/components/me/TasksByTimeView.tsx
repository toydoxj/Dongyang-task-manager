"use client";

import Link from "next/link";

import type { Project, Task } from "@/lib/domain";
import { dDayLabel, formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

interface Props {
  tasks: Task[];
  projects: Project[];
  onClickTask: (t: Task) => void;
  onDeleteTask: (t: Task) => void;
  /** MY-003 — task를 즉시 완료 처리. undefined면 quick action ✓ 비활성. */
  onCompleteTask?: (t: Task) => void;
}

function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function startOfWeekMonday(d: Date): Date {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  const day = x.getDay() || 7;
  x.setDate(x.getDate() - (day - 1));
  return x;
}

type GroupKey = "overdue" | "today" | "thisWeek" | "later" | "recentDone";

const GROUP_META: Record<
  GroupKey,
  { label: string; tone: string; emptyHint: string }
> = {
  overdue: {
    label: "지연",
    tone: "border-red-400 bg-red-50 dark:border-red-700 dark:bg-red-950/30",
    emptyHint: "지연된 업무가 없습니다.",
  },
  today: {
    label: "오늘 마감",
    tone: "border-amber-400 bg-amber-50 dark:border-amber-700 dark:bg-amber-950/30",
    emptyHint: "오늘 마감 업무가 없습니다.",
  },
  thisWeek: {
    label: "이번 주 마감",
    tone: "border-blue-400 bg-blue-50 dark:border-blue-700 dark:bg-blue-950/30",
    emptyHint: "이번 주 마감 업무가 없습니다.",
  },
  later: {
    label: "이후·미정",
    tone: "border-zinc-300 bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900",
    emptyHint: "이후 마감/미정 업무가 없습니다.",
  },
  recentDone: {
    label: "최근 완료",
    tone: "border-emerald-300 bg-emerald-50 dark:border-emerald-700 dark:bg-emerald-950/30",
    emptyHint: "최근 완료된 업무가 없습니다.",
  },
};

/** MY-002 — TodayTasks의 분류(category) view에 대비되는 시간 축 view.
 * 5개 그룹: 지연 / 오늘 / 이번 주 / 이후·미정 / 최근 완료. */
export default function TasksByTimeView({
  tasks,
  projects,
  onClickTask,
  onDeleteTask,
  onCompleteTask,
}: Props) {
  const today = new Date();
  const todayStr = ymd(today);
  const weekStart = startOfWeekMonday(today);
  const weekEnd = new Date(weekStart);
  weekEnd.setDate(weekEnd.getDate() + 7);
  const weekEndStr = ymd(weekEnd);

  const projectByNorm = new Map<string, Project>();
  const norm = (id: string): string => id.replace(/-/g, "").toLowerCase();
  for (const p of projects) projectByNorm.set(norm(p.id), p);

  const groups: Record<GroupKey, Task[]> = {
    overdue: [],
    today: [],
    thisWeek: [],
    later: [],
    recentDone: [],
  };

  for (const t of tasks) {
    if (t.status === "완료") {
      groups.recentDone.push(t);
      continue;
    }
    const d = t.end_date ? t.end_date.slice(0, 10) : null;
    if (d == null) {
      groups.later.push(t);
    } else if (d < todayStr) {
      groups.overdue.push(t);
    } else if (d === todayStr) {
      groups.today.push(t);
    } else if (d < weekEndStr) {
      groups.thisWeek.push(t);
    } else {
      groups.later.push(t);
    }
  }

  // 정렬: 지연/오늘/이번주는 마감일 가까운 순, 이후·미정은 마감일 오름차순(미정 뒤),
  // 최근 완료는 actual_end_date 내림차순.
  const byEndAsc = (a: Task, b: Task): number => {
    const ad = a.end_date ?? "9999-12-31";
    const bd = b.end_date ?? "9999-12-31";
    return ad.localeCompare(bd);
  };
  const byCompletedDesc = (a: Task, b: Task): number => {
    const ad = a.actual_end_date ?? a.last_edited_time ?? "";
    const bd = b.actual_end_date ?? b.last_edited_time ?? "";
    return bd.localeCompare(ad);
  };
  groups.overdue.sort(byEndAsc);
  groups.today.sort(byEndAsc);
  groups.thisWeek.sort(byEndAsc);
  groups.later.sort(byEndAsc);
  groups.recentDone.sort(byCompletedDesc);

  return (
    <div className="space-y-3">
      {(Object.keys(GROUP_META) as GroupKey[]).map((key) => {
        const meta = GROUP_META[key];
        const list = groups[key];
        return (
          <section
            key={key}
            className={cn(
              "rounded-lg border p-3",
              meta.tone,
            )}
          >
            <header className="mb-2 flex items-center justify-between">
              <h3 className="text-xs font-semibold text-zinc-800 dark:text-zinc-200">
                {meta.label}
                <span className="ml-1.5 text-zinc-500">({list.length})</span>
              </h3>
            </header>
            {list.length === 0 ? (
              <p className="py-2 text-center text-[11px] text-zinc-400">
                {meta.emptyHint}
              </p>
            ) : (
              <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
                {list.map((t) => (
                  <TaskRow
                    key={t.id}
                    task={t}
                    project={projectByNorm.get(norm(t.project_ids[0] ?? ""))}
                    onClick={() => onClickTask(t)}
                    onDelete={() => onDeleteTask(t)}
                    onComplete={
                      onCompleteTask && key !== "recentDone"
                        ? () => onCompleteTask(t)
                        : undefined
                    }
                    showDDay={key !== "recentDone"}
                  />
                ))}
              </ul>
            )}
          </section>
        );
      })}
    </div>
  );
}

function TaskRow({
  task,
  project,
  onClick,
  onDelete,
  onComplete,
  showDDay,
}: {
  task: Task;
  project: Project | undefined;
  onClick: () => void;
  onDelete: () => void;
  onComplete?: () => void;
  showDDay: boolean;
}) {
  const dateStr = task.end_date
    ? formatDate(task.end_date)
    : task.actual_end_date
      ? formatDate(task.actual_end_date)
      : "—";
  const projectId = task.project_ids[0];
  return (
    <li className="flex items-center gap-2 py-1.5 text-xs">
      <button
        type="button"
        onClick={onClick}
        className="flex min-w-0 flex-1 items-center gap-2 text-left hover:underline"
        title={task.title}
      >
        <span className="truncate font-medium text-zinc-800 dark:text-zinc-200">
          {task.title || "(제목 없음)"}
        </span>
        {project && (
          <span className="shrink-0 text-[10px] text-zinc-500">
            · {project.code || project.name}
          </span>
        )}
      </button>
      <span className="shrink-0 font-mono text-[10px] text-zinc-500">
        {dateStr}
      </span>
      {showDDay && task.end_date && (
        <span className="shrink-0 rounded bg-zinc-100 px-1 text-[10px] text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
          {dDayLabel(task.end_date)}
        </span>
      )}
      {/* MY-003 quick action — 완료 처리 / 프로젝트 / 날인 */}
      {onComplete && (
        <button
          type="button"
          onClick={onComplete}
          title="완료 처리"
          className="shrink-0 rounded px-1.5 text-emerald-600 hover:bg-emerald-100 dark:text-emerald-400 dark:hover:bg-emerald-900/30"
        >
          ✓
        </button>
      )}
      {projectId && (
        <Link
          href={`/projects/${projectId}`}
          title="프로젝트 열기"
          className="shrink-0 rounded px-1.5 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800"
        >
          📁
        </Link>
      )}
      {projectId && (
        <Link
          href={`/seal-requests?project_id=${projectId}`}
          title="관련 날인"
          className="shrink-0 rounded px-1.5 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800"
        >
          🔖
        </Link>
      )}
      <button
        type="button"
        onClick={onDelete}
        title="삭제"
        className="shrink-0 rounded px-1 text-zinc-400 hover:bg-red-100 hover:text-red-600 dark:hover:bg-red-900/30"
      >
        ×
      </button>
    </li>
  );
}
