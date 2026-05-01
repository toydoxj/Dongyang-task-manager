"use client";

import {
  DndContext,
  type DragEndEvent,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import { useEffect, useMemo, useState } from "react";

import { updateTask } from "@/lib/api";
import type { Task } from "@/lib/domain";
import { TASK_STATUSES } from "@/lib/domain";
import { dDayLabel, formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

import TaskEditModal from "./TaskEditModal";

interface Props {
  tasks: Task[];
  onChanged: () => void;
  onCreate?: (initialStatus?: string) => void;
}

const STATUS_COLOR: Record<string, string> = {
  "시작 전": "border-zinc-300 dark:border-zinc-700",
  "진행 중": "border-blue-500/50",
  "완료": "border-emerald-500/50",
  "보류": "border-pink-500/50",
};

interface UndoEntry {
  taskId: string;
  taskTitle: string;
  prev: {
    status: string;
  };
}

const todayISO = (): string => new Date().toISOString().slice(0, 10);

export default function TaskKanban({ tasks, onChanged, onCreate }: Props) {
  const [editing, setEditing] = useState<Task | null>(null);
  const [, setUndoStack] = useState<UndoEntry[]>([]);
  const [toast, setToast] = useState<string | null>(null);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
  );

  // 프로젝트 상세 칸반은 기간과 무관하게 모든 task 표시 (사용자 정책).
  const { grouped, hiddenCompleted } = useMemo(() => {
    const g = new Map<string, Task[]>();
    for (const s of TASK_STATUSES) g.set(s, []);
    for (const t of tasks) {
      const key = TASK_STATUSES.includes(
        t.status as (typeof TASK_STATUSES)[number],
      )
        ? t.status
        : "시작 전";
      g.get(key)?.push(t);
    }
    return { grouped: g, hiddenCompleted: 0 };
  }, [tasks]);

  const showToast = (msg: string): void => {
    setToast(msg);
    window.setTimeout(() => setToast(null), 2500);
  };

  const pushUndo = (task: Task): void => {
    setUndoStack((s) => [
      ...s.slice(-19),
      {
        taskId: task.id,
        taskTitle: task.title,
        prev: { status: task.status },
      },
    ]);
  };

  const applyStatusChange = async (
    task: Task,
    newStatus: string,
  ): Promise<void> => {
    pushUndo(task);
    const patch: Parameters<typeof updateTask>[1] = { status: newStatus };
    if (newStatus === "완료") {
      patch.actual_end_date = todayISO();
    }
    await updateTask(task.id, patch);
    onChanged();
    showToast(`"${task.title || "(제목 없음)"}" → ${newStatus}  (Ctrl+Z 되돌리기)`);
  };

  const handleDragEnd = (e: DragEndEvent): void => {
    const { active, over } = e;
    if (!over) return;
    const newStatus = (over.data.current as { status?: string })?.status;
    const task = (active.data.current as { task?: Task })?.task;
    if (!task || !newStatus || task.status === newStatus) return;
    void applyStatusChange(task, newStatus);
  };

  // Ctrl+Z 되돌리기
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const ctrlOrMeta = e.ctrlKey || e.metaKey;
      if (!ctrlOrMeta || e.shiftKey || e.key.toLowerCase() !== "z") return;
      // input/textarea 안에서는 기본 undo 동작 유지
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea" || target?.isContentEditable) return;
      e.preventDefault();
      setUndoStack((stack) => {
        const last = stack[stack.length - 1];
        if (!last) {
          showToast("되돌릴 항목이 없습니다");
          return stack;
        }
        void (async () => {
          await updateTask(last.taskId, { status: last.prev.status });
          onChanged();
          showToast(`"${last.taskTitle || "(제목 없음)"}" 되돌림 → ${last.prev.status}`);
        })();
        return stack.slice(0, -1);
      });
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onChanged]);

  return (
    <div className="relative rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <header className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">업무 TASK ({tasks.length})</h3>
        </div>
        {onCreate && (
          <button
            type="button"
            onClick={() => onCreate()}
            className="rounded-md border border-zinc-300 px-2.5 py-1 text-xs hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
          >
            + 새 업무
          </button>
        )}
      </header>

      <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4">
          {TASK_STATUSES.map((status) => (
            <DroppableColumn
              key={status}
              status={status}
              items={grouped.get(status) ?? []}
              hiddenCount={status === "완료" ? hiddenCompleted : 0}
              onAdvance={(t, next) => void applyStatusChange(t, next)}
              onClickTask={setEditing}
              onCreate={onCreate}
            />
          ))}
        </div>
      </DndContext>

      <TaskEditModal
        task={editing}
        onClose={() => setEditing(null)}
        onSaved={onChanged}
      />

      {toast && (
        <div className="pointer-events-none fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-md bg-zinc-900 px-3 py-2 text-xs text-white shadow-lg dark:bg-zinc-100 dark:text-zinc-900">
          {toast}
        </div>
      )}
    </div>
  );
}

function DroppableColumn({
  status,
  items,
  hiddenCount,
  onAdvance,
  onClickTask,
  onCreate,
}: {
  status: string;
  items: Task[];
  hiddenCount: number;
  onAdvance: (t: Task, nextStatus: string) => void;
  onClickTask: (t: Task) => void;
  onCreate?: (initialStatus?: string) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({
    id: `col-${status}`,
    data: { status },
  });

  return (
    <div
      ref={setNodeRef}
      className={cn(
        "rounded-lg border bg-zinc-50/50 p-2 transition-colors dark:bg-zinc-950/50",
        STATUS_COLOR[status],
        isOver && "bg-blue-500/5 ring-2 ring-blue-400/60",
      )}
    >
      <div className="mb-2 flex items-center justify-between px-1">
        <h4 className="text-xs font-semibold">{status}</h4>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-zinc-500">
            {items.length}
            {hiddenCount > 0 && (
              <span
                className="ml-1 text-zinc-400"
                title={`최근 10일 이전 완료 ${hiddenCount}건은 숨김`}
              >
                (+{hiddenCount})
              </span>
            )}
          </span>
          {onCreate && (
            <button
              type="button"
              onClick={() => onCreate(status)}
              title={`${status} 상태로 새 업무 생성`}
              className="rounded border border-zinc-300 px-1.5 py-0.5 text-[10px] leading-none hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
            >
              +
            </button>
          )}
        </div>
      </div>
      <ul className="min-h-[60px] space-y-1.5">
        {items.length === 0 && (
          <li className="px-1 py-3 text-center text-[10px] text-zinc-400">
            {onCreate ? "+ 추가 또는 카드 드롭" : "비어있음"}
          </li>
        )}
        {items.map((t) => (
          <DraggableCard
            key={t.id}
            task={t}
            currentStatus={status}
            onAdvance={onAdvance}
            onClick={() => onClickTask(t)}
          />
        ))}
      </ul>
    </div>
  );
}

function DraggableCard({
  task,
  currentStatus,
  onAdvance,
  onClick,
}: {
  task: Task;
  currentStatus: string;
  onAdvance: (t: Task, nextStatus: string) => void;
  onClick: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } =
    useDraggable({
      id: task.id,
      data: { task, status: currentStatus },
    });

  const idx = TASK_STATUSES.indexOf(
    currentStatus as (typeof TASK_STATUSES)[number],
  );
  const next =
    idx >= 0 && idx < TASK_STATUSES.length - 1 ? TASK_STATUSES[idx + 1] : null;

  const due = task.end_date;

  return (
    <li
      ref={setNodeRef}
      style={{
        transform: CSS.Translate.toString(transform),
        opacity: isDragging ? 0.4 : 1,
      }}
      {...attributes}
      {...listeners}
      onClick={onClick}
      className={cn(
        "cursor-grab rounded-md border border-zinc-200 bg-white p-2 text-xs shadow-sm transition-shadow active:cursor-grabbing dark:border-zinc-800 dark:bg-zinc-900",
        !isDragging &&
          "hover:bg-zinc-50 hover:shadow-md dark:hover:bg-zinc-800/50",
        isDragging && "ring-2 ring-blue-400/60",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="min-w-0 flex-1 truncate font-medium" title={task.title}>
          {task.title || "(제목 없음)"}
        </p>
        {next && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onAdvance(task, next);
            }}
            onPointerDown={(e) => e.stopPropagation()}
            title={`다음 상태 → ${next}`}
            className="shrink-0 rounded border border-zinc-300 px-1.5 py-0.5 text-[10px] hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
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
      <div className="mt-1.5 flex items-center justify-between text-[10px] text-zinc-500">
        <span>{formatDate(due)}</span>
        {due && currentStatus !== "완료" && (
          <span className="font-medium">{dDayLabel(due)}</span>
        )}
      </div>
    </li>
  );
}
