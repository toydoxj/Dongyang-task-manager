"use client";

import { useState } from "react";

import Modal from "@/components/ui/Modal";
import { useAuth } from "@/components/AuthGuard";
import { createTask } from "@/lib/api";
import type { Project } from "@/lib/domain";
import {
  TASK_CATEGORIES,
  TASK_DIFFICULTIES,
  TASK_PRIORITIES,
  TASK_STATUSES,
  TIME_BASED_CATEGORIES,
} from "@/lib/domain";

interface Props {
  open: boolean;
  /** 프로젝트 컨텍스트가 정해진 호출(프로젝트 상세 등). 없으면 선택 dropdown 노출. */
  projectId?: string;
  /** 비프로젝트 모드일 때 사용자가 고를 수 있는 프로젝트 목록 (담당 프로젝트 등). */
  projects?: Project[];
  initialStatus?: string;
  onClose: () => void;
  onCreated: () => void;
}

export default function TaskCreateModal({
  open,
  projectId = "",
  projects,
  initialStatus,
  onClose,
  onCreated,
}: Props) {
  if (!open) return null;
  return (
    <Form
      key={`${projectId}:${initialStatus ?? ""}`}
      projectId={projectId}
      projects={projects}
      initialStatus={initialStatus}
      onClose={onClose}
      onCreated={onCreated}
    />
  );
}

function Form({
  projectId,
  projects,
  initialStatus,
  onClose,
  onCreated,
}: {
  projectId: string;
  projects?: Project[];
  initialStatus?: string;
  onClose: () => void;
  onCreated: () => void;
}) {
  const { user } = useAuth();
  const today = new Date().toISOString().slice(0, 10);
  const [title, setTitle] = useState("");
  const [status, setStatus] = useState(initialStatus || "시작 전");
  const [start, setStart] = useState(today);
  const [end, setEnd] = useState("");
  const [priority, setPriority] = useState("");
  const [difficulty, setDifficulty] = useState("");
  // 프로젝트 컨텍스트가 있으면 default '프로젝트', 없으면 미분류
  const [category, setCategory] = useState(projectId ? "프로젝트" : "");
  // 분류=프로젝트 + projectId 미지정인 경우(=/me에서 새 업무) 사용자가 dropdown으로 선택
  const [pickedProjectId, setPickedProjectId] = useState(projectId);
  const [assignees, setAssignees] = useState(user?.name ?? "");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const showProjectPicker = category === "프로젝트" && !projectId;
  const isTimeBased = TIME_BASED_CATEGORIES.includes(category);

  const submit = async (): Promise<void> => {
    if (!title.trim()) {
      setError("제목을 입력하세요");
      return;
    }
    const finalProjectId = projectId || pickedProjectId;
    if (category === "프로젝트" && !finalProjectId) {
      setError("분류가 '프로젝트'면 프로젝트를 선택하세요");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await createTask({
        title: title.trim(),
        project_id: category === "프로젝트" ? finalProjectId : "",
        category: category || undefined,
        status,
        start_date: start || undefined,
        end_date: end || undefined,
        priority: priority || undefined,
        difficulty: difficulty || undefined,
        assignees: assignees
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        note: note || undefined,
      });
      onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "생성 실패");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={true} onClose={onClose} title="새 업무 TASK" size="md">
      <div className="space-y-3">
        <Field label="제목" required>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className={inputCls}
            placeholder="예: 1차 도면 검토"
            autoFocus
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
              onChange={(e) => {
                const next = e.target.value;
                const wasTime = TIME_BASED_CATEGORIES.includes(category);
                const nowTime = TIME_BASED_CATEGORIES.includes(next);
                if (wasTime !== nowTime) {
                  // date ↔ datetime-local 형식 변환
                  if (nowTime) {
                    if (start && !start.includes("T")) setStart(`${start}T09:00`);
                    if (end && !end.includes("T")) setEnd(`${end}T18:00`);
                  } else {
                    if (start.includes("T")) setStart(start.slice(0, 10));
                    if (end.includes("T")) setEnd(end.slice(0, 10));
                  }
                }
                setCategory(next);
              }}
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
        </div>

        {showProjectPicker && (
          <Field label="프로젝트" required>
            <select
              value={pickedProjectId}
              onChange={(e) => setPickedProjectId(e.target.value)}
              className={inputCls}
            >
              <option value="">— 선택하세요</option>
              {(projects ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.code ? `[${p.code}] ` : ""}{p.name}
                </option>
              ))}
            </select>
          </Field>
        )}

        <div className="grid grid-cols-2 gap-3">
          <Field label={isTimeBased ? "시작 일시" : "시작일"}>
            <input
              type={isTimeBased ? "datetime-local" : "date"}
              value={start}
              onChange={(e) => {
                const v = e.target.value;
                // 완료일이 비어있거나 이전 시작일과 같으면 자동 동기화
                if (!end || end === start) setEnd(v);
                setStart(v);
              }}
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
            rows={2}
            className={`${inputCls} resize-y`}
          />
        </Field>

        {error && (
          <p className="rounded-md border border-red-500/40 bg-red-500/5 p-2 text-xs text-red-400">
            {error}
          </p>
        )}

        <footer className="flex justify-end gap-2 pt-2">
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
            onClick={submit}
            disabled={busy}
            className="rounded-md bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
          >
            {busy ? "생성 중..." : "생성"}
          </button>
        </footer>
      </div>
    </Modal>
  );
}

const inputCls =
  "w-full rounded-md border border-zinc-300 bg-white px-2.5 py-1.5 text-sm outline-none focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-950";

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-zinc-500">
        {label}
        {required && <span className="ml-1 text-red-500">*</span>}
      </span>
      {children}
    </label>
  );
}
