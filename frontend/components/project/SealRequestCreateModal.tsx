"use client";

import { useRef, useState } from "react";

import { useAuth } from "@/components/AuthGuard";
import Modal from "@/components/ui/Modal";
import { createSealRequest } from "@/lib/api";
import type { Project } from "@/lib/domain";
import { useProjects } from "@/lib/hooks";

const SEAL_TYPES = ["구조계산서", "도면", "검토서", "기타"] as const;

interface Props {
  open: boolean;
  /** 프로젝트 컨텍스트 고정 (프로젝트 상세에서 호출 시). */
  fixedProject?: Project | null;
  onClose: () => void;
  onCreated: () => void;
}

export default function SealRequestCreateModal({
  open,
  fixedProject,
  onClose,
  onCreated,
}: Props) {
  if (!open) return null;
  return (
    <Form
      key={fixedProject?.id ?? "new"}
      fixedProject={fixedProject}
      onClose={onClose}
      onCreated={onCreated}
    />
  );
}

function Form({
  fixedProject,
  onClose,
  onCreated,
}: {
  fixedProject?: Project | null;
  onClose: () => void;
  onCreated: () => void;
}) {
  const { user } = useAuth();
  // 고정 프로젝트가 없으면 본인 담당 프로젝트 dropdown
  const { data: projectData } = useProjects(
    !fixedProject && user?.name ? { mine: true } : undefined,
    !fixedProject,
  );
  const myProjects = projectData?.items ?? [];

  const [projectId, setProjectId] = useState(fixedProject?.id ?? "");
  const [sealType, setSealType] = useState<string>("구조계산서");
  const [title, setTitle] = useState("");
  const [note, setNote] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const submit = async (): Promise<void> => {
    if (!projectId) {
      setErr("프로젝트를 선택하세요");
      return;
    }
    if (files.length === 0) {
      setErr("첨부파일을 1개 이상 추가하세요");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const fd = new FormData();
      fd.append("project_id", projectId);
      fd.append("seal_type", sealType);
      fd.append("title", title);
      fd.append("note", note);
      for (const f of files) fd.append("files", f);
      await createSealRequest(fd);
      onCreated();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "등록 실패");
    } finally {
      setBusy(false);
    }
  };

  const onPickFiles = (list: FileList | null): void => {
    if (!list) return;
    setFiles((prev) => [...prev, ...Array.from(list)]);
    if (fileInput.current) fileInput.current.value = "";
  };

  return (
    <Modal open onClose={onClose} title="새 날인요청" size="md">
      <div className="space-y-3">
        <Field label="프로젝트" required>
          {fixedProject ? (
            <p className="rounded-md border border-zinc-200 bg-zinc-50 px-2.5 py-1.5 text-sm dark:border-zinc-800 dark:bg-zinc-900">
              {fixedProject.code ? `[${fixedProject.code}] ` : ""}
              {fixedProject.name}
            </p>
          ) : (
            <select
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
              className={inputCls}
            >
              <option value="">— 선택하세요</option>
              {myProjects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.code ? `[${p.code}] ` : ""}
                  {p.name}
                </option>
              ))}
            </select>
          )}
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="날인유형" required>
            <select
              value={sealType}
              onChange={(e) => setSealType(e.target.value)}
              className={inputCls}
            >
              {SEAL_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </Field>
          <Field label="제목 (선택)">
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="비워두면 자동 생성"
              className={inputCls}
            />
          </Field>
        </div>

        <Field label="비고">
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={3}
            className={`${inputCls} resize-y`}
          />
        </Field>

        <Field label="첨부파일 (다중 가능, 파일당 ≤20MB)" required>
          <input
            ref={fileInput}
            type="file"
            multiple
            onChange={(e) => onPickFiles(e.target.files)}
            className="block w-full text-xs file:mr-2 file:rounded-md file:border-0 file:bg-zinc-100 file:px-3 file:py-1.5 file:text-xs hover:file:bg-zinc-200 dark:file:bg-zinc-800 dark:file:text-zinc-100"
          />
          {files.length > 0 && (
            <ul className="mt-2 space-y-1 text-xs">
              {files.map((f, i) => (
                <li
                  key={i}
                  className="flex items-center justify-between rounded border border-zinc-200 px-2 py-1 dark:border-zinc-800"
                >
                  <span className="truncate" title={f.name}>
                    📎 {f.name}{" "}
                    <span className="text-zinc-400">
                      ({Math.round(f.size / 1024)} KB)
                    </span>
                  </span>
                  <button
                    type="button"
                    onClick={() =>
                      setFiles((prev) => prev.filter((_, j) => j !== i))
                    }
                    className="text-zinc-400 hover:text-red-500"
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Field>

        {err && (
          <p className="rounded-md border border-red-500/40 bg-red-500/5 p-2 text-xs text-red-400">
            {err}
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
            {busy ? "등록 중..." : "등록"}
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
