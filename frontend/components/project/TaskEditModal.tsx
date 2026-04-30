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
import { useProjects } from "@/lib/hooks";

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
  // datetime-local input은 'YYYY-MM-DDTHH:mm' (timezone 없는 wall clock).
  // 노션은 UTC ISO('+00:00' 또는 'Z')로 저장하므로 KST로 변환 후 잘라야 한다.
  // (변환 없이 slice만 하면 UTC 00:00 → input에 12 AM으로 표시되는 버그)
  const normalizeForInput = (s: string | null): string => {
    if (!s) return "";
    if (!s.includes("T")) return s;
    const d = new Date(s);
    if (Number.isNaN(d.getTime())) return s.slice(0, 16);
    const kstMs = d.getTime() + 9 * 60 * 60 * 1000;
    return new Date(kstMs).toISOString().slice(0, 16);
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
  const [projectId, setProjectId] = useState(task.project_ids[0] ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isTimeBased = isTimeBasedTask(category, activity);
  // 분류=프로젝트일 때만 fetch — ProjectImportModal과 동일 패턴(진행중만, 47건 정도)
  const { data: projectsData } = useProjects(
    { stage: "진행중" },
    category === "프로젝트",
  );
  const projects = projectsData?.items ?? [];
  // 현재 task가 이미 다른 단계의 프로젝트를 가리키면 dropdown에서 사라지지 않도록
  // 그 항목을 fallback으로 보여주는 라벨 (id만으로 표시)
  const wasProjectId = task.project_ids[0] ?? "";
  const wasProjectInList = projects.some((p) => p.id === wasProjectId);

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
      const wasProjectId = task.project_ids[0] ?? "";
      // 분류=프로젝트면 project_ids 동기화. 분류가 프로젝트가 아니면 비우기.
      let projectIdsParam: string[] | undefined;
      if (category === "프로젝트") {
        if (projectId !== wasProjectId) {
          projectIdsParam = projectId ? [projectId] : [];
        }
      } else if (wasProjectId) {
        // 분류가 프로젝트에서 다른 것으로 바뀌었으면 relation 비우기
        projectIdsParam = [];
      }
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
        project_ids: projectIdsParam,
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
    if (
      !confirm(
        `"${task.title}" 업무를 삭제하시겠습니까?\n노션에서 보관 처리됩니다 (영구 삭제는 노션에서 가능).`,
      )
    )
      return;
    setBusy(true);
    try {
      await archiveTask(task.id);
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "삭제 실패");
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

        {category === "프로젝트" && (
          <Field label="프로젝트">
            <select
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
              className={inputCls}
            >
              <option value="">
                {projectsData ? "— 선택 (진행중)" : "프로젝트 불러오는 중…"}
              </option>
              {/* 진행중에 없는 옛 프로젝트는 별도 표시 (이전 선택 보존용) */}
              {wasProjectId && !wasProjectInList && (
                <option value={wasProjectId}>
                  (현재 선택 — 진행중 외 프로젝트)
                </option>
              )}
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.code ? `[${p.code}] ` : ""}
                  {p.name || "(제목 없음)"}
                </option>
              ))}
            </select>
            <p className="mt-1 text-[10px] text-zinc-500">
              진행중 프로젝트만 표시됩니다.
            </p>
          </Field>
        )}

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
            title="노션에서 보관 처리됩니다"
          >
            삭제
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
