"use client";

import { useState } from "react";

import Modal from "@/components/ui/Modal";
import { archiveTask, updateTask } from "@/lib/api";
import type { Task } from "@/lib/domain";
import {
  ACTIVITY_TYPES,
  isTimeBasedTask,
  TASK_CATEGORIES,
  TASK_DIFFICULTIES,
  TASK_PRIORITIES,
  TASK_STATUSES,
} from "@/lib/domain";

interface Props {
  task: Task | null;
  onClose: () => void;
  onSaved: () => void;
}

export default function TaskEditModal({ task, onClose, onSaved }: Props) {
  if (!task) return null;
  // task 가 바뀔 때마다 새로 마운트 (useEffect setState 회피)
  return (
    <Form key={task.id} task={task} onClose={onClose} onSaved={onSaved} />
  );
}

function Form({
  task,
  onClose,
  onSaved,
}: {
  task: Task;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [title, setTitle] = useState(task.title ?? "");
  const [status, setStatus] = useState(task.status || "시작 전");
  // datetime-local input은 'YYYY-MM-DDTHH:mm' 형식. 기존 ISO datetime이면 잘라서 사용.
  const normalizeForInput = (s: string | null): string => {
    if (!s) return "";
    if (s.includes("T")) return s.slice(0, 16); // YYYY-MM-DDTHH:mm
    return s;
  };
  const [start, setStart] = useState(normalizeForInput(task.start_date));
  const [end, setEnd] = useState(normalizeForInput(task.end_date));
  const [actualEnd, setActualEnd] = useState(task.actual_end_date ?? "");
  const [priority, setPriority] = useState(task.priority ?? "");
  const [difficulty, setDifficulty] = useState(task.difficulty ?? "");
  const [category, setCategory] = useState(task.category ?? "");
  const [activity, setActivity] = useState(task.activity ?? "");
  const [assignees, setAssignees] = useState(task.assignees.join(", "));
  const [note, setNote] = useState(task.note ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isTimeBased = isTimeBasedTask(category, activity);

  const syncDateTimeFormat = (wasTime: boolean, nowTime: boolean): void => {
    if (wasTime === nowTime) return;
    if (nowTime) {
      if (start && !start.includes("T")) setStart(`${start}T09:00`);
      if (end && !end.includes("T")) setEnd(`${end}T18:00`);
    } else {
      if (start.includes("T")) setStart(start.slice(0, 10));
      if (end.includes("T")) setEnd(end.slice(0, 10));
    }
  };

  const onChangeCategory = (next: string): void => {
    syncDateTimeFormat(
      isTimeBasedTask(category, activity),
      isTimeBasedTask(next, activity),
    );
    setCategory(next);
  };
  const onChangeActivity = (next: string): void => {
    syncDateTimeFormat(
      isTimeBasedTask(category, activity),
      isTimeBasedTask(category, next),
    );
    setActivity(next);
  };

  const save = async (): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      // 빈 문자열은 명시적 'clear' 신호로 backend에 그대로 전송 (None 처리).
      // 원본과 동일하면 변경 없음으로 undefined.
      const wasStart = task.start_date ?? "";
      const wasEnd = task.end_date ?? "";
      const wasActual = task.actual_end_date ?? "";
      const wasPriority = task.priority ?? "";
      const wasDifficulty = task.difficulty ?? "";
      const wasCategory = task.category ?? "";
      const wasActivity = task.activity ?? "";
      await updateTask(task.id, {
        title,
        status,
        start_date: start === wasStart ? undefined : start,
        end_date: end === wasEnd ? undefined : end,
        actual_end_date: actualEnd === wasActual ? undefined : actualEnd,
        priority: priority === wasPriority ? undefined : priority,
        difficulty: difficulty === wasDifficulty ? undefined : difficulty,
        category: category === wasCategory ? undefined : category,
        activity: activity === wasActivity ? undefined : activity,
        assignees: assignees
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        note,
      });
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "저장 실패");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (): Promise<void> => {
    if (!confirm(`"${task.title}" 업무를 보관 처리할까요? (노션 archive)`))
      return;
    setBusy(true);
    try {
      await archiveTask(task.id);
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "보관 실패");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={true} onClose={onClose} title="업무 TASK 편집" size="md">
      <div className="space-y-4">
        <Field label="제목">
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className={inputCls}
          />
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="상태">
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className={inputCls}
            >
              {TASK_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </Field>
          <Field label="우선순위">
            <select
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
              className={inputCls}
            >
              <option value="">—</option>
              {TASK_PRIORITIES.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </Field>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Field label="분류">
            <select
              value={category}
              onChange={(e) => onChangeCategory(e.target.value)}
              className={inputCls}
            >
              <option value="">— 미분류</option>
              {TASK_CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </Field>
          <Field label="활동">
            <select
              value={activity}
              onChange={(e) => onChangeActivity(e.target.value)}
              className={inputCls}
            >
              <option value="">—</option>
              {ACTIVITY_TYPES.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </Field>
        </div>

        <Field label="난이도">
          <select
            value={difficulty}
            onChange={(e) => setDifficulty(e.target.value)}
            className={inputCls}
          >
            <option value="">—</option>
            {TASK_DIFFICULTIES.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label={isTimeBased ? "시작 일시" : "시작일"}>
            <input
              type={isTimeBased ? "datetime-local" : "date"}
              value={start}
              onChange={(e) => setStart(e.target.value)}
              className={inputCls}
            />
          </Field>
          <Field label={isTimeBased ? "종료 일시" : "예상 완료일"}>
            <input
              type={isTimeBased ? "datetime-local" : "date"}
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              className={inputCls}
            />
          </Field>
        </div>

        <Field label="실제 완료일 (완료 시)">
          <input
            type="date"
            value={actualEnd}
            onChange={(e) => setActualEnd(e.target.value)}
            className={inputCls}
          />
        </Field>

        <Field label="담당자 (쉼표로 구분)">
          <input
            type="text"
            value={assignees}
            onChange={(e) => setAssignees(e.target.value)}
            placeholder="홍길동, 김철수"
            className={inputCls}
          />
        </Field>

        <Field label="비고">
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={3}
            className={`${inputCls} resize-y`}
          />
        </Field>

        {error && (
          <p className="rounded-md border border-red-500/40 bg-red-500/5 p-2 text-xs text-red-400">
            {error}
          </p>
        )}

        <footer className="flex items-center justify-between gap-2 pt-2">
          <button
            type="button"
            onClick={remove}
            disabled={busy}
            className="text-xs text-red-500 hover:underline disabled:opacity-50"
          >
            보관 (archive)
          </button>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={busy}
              className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
            >
              취소
            </button>
            <button
              type="button"
              onClick={save}
              disabled={busy}
              className="rounded-md bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
            >
              {busy ? "저장 중..." : "저장"}
            </button>
          </div>
        </footer>
      </div>
    </Modal>
  );
}

const inputCls =
  "w-full rounded-md border border-zinc-300 bg-white px-2.5 py-1.5 text-sm outline-none focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-950";

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-zinc-500">{label}</span>
      {children}
    </label>
  );
}
