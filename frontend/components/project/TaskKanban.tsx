"use client";

import { useState } from "react";

import { updateTask } from "@/lib/api";
import type { Task } from "@/lib/domain";
import { TASK_STATUSES } from "@/lib/domain";
import { dDayLabel, formatDate, formatPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

import TaskEditModal from "./TaskEditModal";

interface Props {
  tasks: Task[];
  onChanged: () => void;
  onCreate?: () => void; // 신규 생성 버튼 (옵션)
}

const STATUS_COLOR: Record<string, string> = {
  "시작 전": "border-zinc-300 dark:border-zinc-700",
  "진행 중": "border-blue-500/50",
  "완료": "border-emerald-500/50",
  "보류": "border-pink-500/50",
};

export default function TaskKanban({ tasks, onChanged, onCreate }: Props) {
  const [editing, setEditing] = useState<Task | null>(null);

  const grouped = new Map<string, Task[]>();
  for (const s of TASK_STATUSES) grouped.set(s, []);
  for (const t of tasks) {
    const key = TASK_STATUSES.includes(t.status as (typeof TASK_STATUSES)[number])
      ? t.status
      : "시작 전";
    grouped.get(key)?.push(t);
  }

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <header className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">업무 TASK ({tasks.length})</h3>
          <p className="text-[10px] text-zinc-500">
            카드 클릭 = 편집, → 버튼 = 다음 상태로 빠르게
          </p>
        </div>
        {onCreate && (
          <button
            type="button"
            onClick={onCreate}
            className="rounded-md border border-zinc-300 px-2.5 py-1 text-xs hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
          >
            + 새 업무
          </button>
        )}
      </header>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4">
        {TASK_STATUSES.map((status) => {
          const items = grouped.get(status) ?? [];
          return (
            <div
              key={status}
              className={cn(
                "rounded-lg border bg-zinc-50/50 p-2 dark:bg-zinc-950/50",
                STATUS_COLOR[status],
              )}
            >
              <div className="mb-2 flex items-center justify-between px-1">
                <h4 className="text-xs font-semibold">{status}</h4>
                <span className="text-[10px] text-zinc-500">{items.length}</span>
              </div>
              <ul className="space-y-1.5">
                {items.length === 0 && (
                  <li className="px-1 py-3 text-center text-[10px] text-zinc-400">
                    비어있음
                  </li>
                )}
                {items.map((t) => (
                  <TaskCardItem
                    key={t.id}
                    task={t}
                    currentStatus={status}
                    onChanged={onChanged}
                    onClick={() => setEditing(t)}
                  />
                ))}
              </ul>
            </div>
          );
        })}
      </div>

      <TaskEditModal
        task={editing}
        onClose={() => setEditing(null)}
        onSaved={onChanged}
      />
    </div>
  );
}

function TaskCardItem({
  task,
  currentStatus,
  onChanged,
  onClick,
}: {
  task: Task;
  currentStatus: string;
  onChanged: () => void;
  onClick: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const idx = TASK_STATUSES.indexOf(currentStatus as (typeof TASK_STATUSES)[number]);
  const next = idx >= 0 && idx < TASK_STATUSES.length - 1 ? TASK_STATUSES[idx + 1] : null;

  const advance = async (e: React.MouseEvent): Promise<void> => {
    e.stopPropagation();
    if (!next) return;
    setBusy(true);
    try {
      await updateTask(task.id, {
        status: next,
        progress: next === "완료" ? 1 : task.progress ?? undefined,
      });
      onChanged();
    } finally {
      setBusy(false);
    }
  };

  const due = task.end_date;
  return (
    <li
      className="cursor-pointer rounded-md border border-zinc-200 bg-white p-2 text-xs transition-colors hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:bg-zinc-800/50"
      onClick={onClick}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="min-w-0 flex-1 truncate font-medium" title={task.title}>
          {task.title || "(제목 없음)"}
        </p>
        {next && (
          <button
            type="button"
            onClick={advance}
            disabled={busy}
            title={`다음 상태 → ${next}`}
            className="shrink-0 rounded border border-zinc-300 px-1.5 py-0.5 text-[10px] hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
          >
            →
          </button>
        )}
      </div>
      {task.assignees.length > 0 && (
        <p className="mt-1 truncate text-[10px] text-zinc-500">
          {task.assignees.join(", ")}
        </p>
      )}
      <div className="mt-1.5 flex items-center justify-between gap-2">
        <ProgressBar value={task.progress} />
        <span className="shrink-0 text-[10px] text-zinc-500">
          {formatPercent(task.progress)}
        </span>
      </div>
      <div className="mt-1 flex items-center justify-between text-[10px] text-zinc-500">
        <span>{formatDate(due)}</span>
        {due && currentStatus !== "완료" && (
          <span className="font-medium">{dDayLabel(due)}</span>
        )}
      </div>
    </li>
  );
}

function ProgressBar({ value }: { value: number | null }) {
  const v = value ?? 0;
  return (
    <div className="h-1 flex-1 rounded-full bg-zinc-200 dark:bg-zinc-800">
      <div
        className="h-full rounded-full bg-blue-500 transition-all"
        style={{ width: `${Math.min(100, Math.max(0, v * 100))}%` }}
      />
    </div>
  );
}
