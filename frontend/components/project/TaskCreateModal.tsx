"use client";

import { useState } from "react";

import Modal from "@/components/ui/Modal";
import { useAuth } from "@/components/AuthGuard";
import { createTask } from "@/lib/api";
import { TASK_PRIORITIES, TASK_STATUSES } from "@/lib/domain";

interface Props {
  open: boolean;
  projectId: string;
  initialStatus?: string;
  onClose: () => void;
  onCreated: () => void;
}

export default function TaskCreateModal({
  open,
  projectId,
  initialStatus,
  onClose,
  onCreated,
}: Props) {
  if (!open) return null;
  return (
    <Form
      key={`${projectId}:${initialStatus ?? ""}`}
      projectId={projectId}
      initialStatus={initialStatus}
      onClose={onClose}
      onCreated={onCreated}
    />
  );
}

function Form({
  projectId,
  initialStatus,
  onClose,
  onCreated,
}: {
  projectId: string;
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
  const [assignees, setAssignees] = useState(user?.name ?? "");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (): Promise<void> => {
    if (!title.trim()) {
      setError("제목을 입력하세요");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await createTask({
        title: title.trim(),
        project_id: projectId,
        status,
        start_date: start || undefined,
        end_date: end || undefined,
        priority: priority || undefined,
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
          <Field label="시작일">
            <input
              type="date"
              value={start}
              onChange={(e) => setStart(e.target.value)}
              className={inputCls}
            />
          </Field>
          <Field label="예상 완료일">
            <input
              type="date"
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
