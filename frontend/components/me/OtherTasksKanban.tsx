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
import { useState } from "react";

import { updateTask } from "@/lib/api";
import type { Task } from "@/lib/domain";
import { dDayLabel, formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

const STATUSES = ["시작 전", "진행 중", "완료", "보류"] as const;
type Status = (typeof STATUSES)[number];

interface Props {
  tasks: Task[];
  onClickTask: (t: Task) => void;
  onDeleteTask: (t: Task) => void;
  onChanged: () => void;
}

export default function OtherTasksKanban({
  tasks,
  onClickTask,
  onDeleteTask,
  onChanged,
}: Props) {
  const [optimistic, setOptimistic] = useState<Map<string, Status>>(new Map());
  const [err, setErr] = useState<string | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
  );

  const grouped = new Map<Status, Task[]>();
  for (const s of STATUSES) grouped.set(s, []);
  for (const t of tasks) {
    const overrideStatus = optimistic.get(t.id);
    const target = (overrideStatus ?? (t.status as Status));
    const bucket = grouped.get(target) ?? grouped.get("시작 전")!;
    bucket.push(t);
  }

  const handleDragEnd = async (e: DragEndEvent): Promise<void> => {
    const { active, over } = e;
    if (!over) return;
    const taskId = String(active.id);
    const target = String(over.id) as Status;
    const t = tasks.find((x) => x.id === taskId);
    if (!t) return;
    const current = optimistic.get(taskId) ?? (t.status as Status);
    if (current === target) return;
    setErr(null);
    setOptimistic((m) => {
      const next = new Map(m);
      next.set(taskId, target);
      return next;
    });
    try {
      await updateTask(taskId, { status: target });
      onChanged();
      // 서버 상태 반영되면 optimistic 제거
      setOptimistic((m) => {
        const next = new Map(m);
        next.delete(taskId);
        return next;
      });
    } catch (ex) {
      setOptimistic((m) => {
        const next = new Map(m);
        next.delete(taskId);
        return next;
      });
      setErr(ex instanceof Error ? ex.message : "상태 변경 실패");
    }
  };

  return (
    <div>
      {err && (
        <p className="mb-2 rounded-md border border-red-500/40 bg-red-500/5 p-2 text-xs text-red-400">
          {err}
        </p>
      )}
      <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {STATUSES.map((s) => (
            <Column
              key={s}
              status={s}
              items={grouped.get(s) ?? []}
              onClickTask={onClickTask}
              onDeleteTask={onDeleteTask}
            />
          ))}
        </div>
      </DndContext>
    </div>
  );
}

function Column({
  status,
  items,
  onClickTask,
  onDeleteTask,
}: {
  status: Status;
  items: Task[];
  onClickTask: (t: Task) => void;
  onDeleteTask: (t: Task) => void;
}) {
  const { isOver, setNodeRef } = useDroppable({ id: status });
  return (
    <div
      ref={setNodeRef}
      className={cn(
        "rounded-xl border bg-white p-3 transition-colors dark:bg-zinc-900",
        isOver
          ? "border-blue-400 ring-1 ring-blue-400"
          : "border-zinc-200 dark:border-zinc-800",
      )}
    >
      <header className="mb-2 flex items-center justify-between">
        <h4 className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">
          {status}
        </h4>
        <span className="text-[10px] text-zinc-500">{items.length}</span>
      </header>
      {items.length === 0 ? (
        <p className="py-4 text-center text-[11px] text-zinc-400">없음</p>
      ) : (
        <ul className="space-y-1.5">
          {items.map((t) => (
            <DraggableCard
              key={t.id}
              task={t}
              onClick={() => onClickTask(t)}
              onDelete={() => onDeleteTask(t)}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function DraggableCard({
  task: t,
  onClick,
  onDelete,
}: {
  task: Task;
  onClick: () => void;
  onDelete: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } =
    useDraggable({ id: t.id });
  const style: React.CSSProperties | undefined = transform
    ? {
        transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`,
        zIndex: 50,
      }
    : undefined;

  const activityBadgeCls =
    t.activity === "외근"
      ? "bg-orange-500/15 text-orange-600 dark:text-orange-400"
      : t.activity === "출장"
        ? "bg-red-500/15 text-red-600 dark:text-red-400"
        : null;

  return (
    <li
      ref={setNodeRef}
      style={style}
      className={cn("touch-none select-none", isDragging && "opacity-60")}
      {...attributes}
      {...listeners}
    >
      <div className="group relative rounded-md border border-zinc-200 bg-white px-2 py-1.5 text-xs hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950 dark:hover:bg-zinc-900">
        <button
          type="button"
          onPointerDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          className="absolute right-1 top-1 hidden rounded p-0.5 text-zinc-400 hover:bg-red-500/15 hover:text-red-500 group-hover:block"
          title="삭제"
        >
          ×
        </button>
        <button type="button" onClick={onClick} className="block w-full text-left">
          <p className="truncate pr-4 font-medium" title={t.title}>
            {t.title || "(제목 없음)"}
          </p>
          <p className="mt-0.5 flex items-center justify-between gap-1 text-[10px] text-zinc-500">
            <span className="truncate">마감 {formatDate(t.end_date)}</span>
            <span className="flex shrink-0 items-center gap-1">
              {activityBadgeCls && (
                <span className={cn("rounded px-1 py-0.5 text-[9px] font-medium", activityBadgeCls)}>
                  {t.activity}
                </span>
              )}
              {t.category && (
                <span className="rounded bg-zinc-100 px-1 py-0.5 text-[9px] text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                  {t.category}
                </span>
              )}
              <span className="rounded bg-zinc-200/60 px-1 py-0.5 text-[9px] font-medium text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
                {dDayLabel(t.end_date) || "—"}
              </span>
            </span>
          </p>
        </button>
      </div>
    </li>
  );
}
