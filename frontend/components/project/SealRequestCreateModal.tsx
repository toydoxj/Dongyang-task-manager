"use client";

import { useMemo, useRef, useState } from "react";

import { useAuth } from "@/components/AuthGuard";
import Modal from "@/components/ui/Modal";
import { createSealRequest } from "@/lib/api";
import type { Project } from "@/lib/domain";
import { useProjects } from "@/lib/hooks";

const SEAL_TYPES = [
  "구조계산서",
  "구조안전확인서",
  "구조검토서",
  "구조도면",
  "보고서",
  "기타",
] as const;
type SealType = (typeof SEAL_TYPES)[number];

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
  const { data: projectData } = useProjects(
    !fixedProject && user?.name ? { mine: true } : undefined,
    !fixedProject,
  );
  const myProjects = projectData?.items ?? [];

  const [projectId, setProjectId] = useState(fixedProject?.id ?? "");
  const [sealType, setSealType] = useState<SealType>("구조계산서");
  const [title, setTitle] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [note, setNote] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  // 조건부 필드
  const [realSource, setRealSource] = useState("");
  const [purpose, setPurpose] = useState("");
  const [revision, setRevision] = useState(0);
  const [withSafetyCert, setWithSafetyCert] = useState(false);
  const [summary, setSummary] = useState("");
  const [docKind, setDocKind] = useState("");

  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const selectedProject = useMemo<Project | null>(() => {
    if (fixedProject) return fixedProject;
    return myProjects.find((p) => p.id === projectId) ?? null;
  }, [fixedProject, myProjects, projectId]);

  const titlePreview = useMemo(() => {
    if (title.trim()) return title.trim();
    const code = (selectedProject?.code || "?").trim();
    switch (sealType) {
      case "구조계산서":
        return `${code}_구조계산서_rev${revision || 0}_${purpose || "?"}`;
      case "구조안전확인서":
        return `${code}_구조안전확인서_${purpose || "?"}`;
      case "구조검토서":
        return `${code}_(자동발급)_구조검토서`;
      case "구조도면":
        return `${code}_구조도면_${purpose || "?"}`;
      case "보고서":
        return `${code}_보고서`;
      case "기타":
        return `${code}_${docKind || "기타"}`;
    }
  }, [title, selectedProject, sealType, revision, purpose, docKind]);

  const submit = async (): Promise<void> => {
    if (!projectId) {
      setErr("프로젝트를 선택하세요");
      return;
    }
    if (!dueDate) {
      setErr("제출 예정일은 필수입니다");
      return;
    }
    if (sealType === "구조계산서" && !purpose.trim()) {
      setErr("구조계산서: 용도를 입력하세요");
      return;
    }
    if (sealType === "구조안전확인서" && !purpose.trim()) {
      setErr("구조안전확인서: 용도를 입력하세요");
      return;
    }
    if (sealType === "구조도면" && !purpose.trim()) {
      setErr("구조도면: 용도를 입력하세요");
      return;
    }
    if (sealType === "기타" && !docKind.trim()) {
      setErr("기타: 문서종류를 입력하세요");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const fd = new FormData();
      fd.append("project_id", projectId);
      fd.append("seal_type", sealType);
      fd.append("title", title);
      fd.append("due_date", dueDate);
      fd.append("note", note);
      fd.append("real_source", realSource);
      fd.append("purpose", purpose);
      fd.append("revision", String(revision || 0));
      fd.append("with_safety_cert", withSafetyCert ? "true" : "false");
      fd.append("summary", summary);
      fd.append("doc_kind", docKind);
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
          <Field label="검토구분" required>
            <select
              value={sealType}
              onChange={(e) => setSealType(e.target.value as SealType)}
              className={inputCls}
            >
              {SEAL_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </Field>
          <Field label="제출 예정일" required>
            <input
              type="date"
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
              className={inputCls}
            />
          </Field>
        </div>

        <Field label="실제출처 (발주처와 다른 경우만)">
          <input
            type="text"
            value={realSource}
            onChange={(e) => setRealSource(e.target.value)}
            placeholder="비워두면 프로젝트의 발주처 사용"
            className={inputCls}
          />
        </Field>

        {/* 검토구분별 조건부 필드 */}
        {sealType === "구조계산서" && (
          <div className="grid grid-cols-3 gap-3 rounded-md border border-zinc-200 p-2 dark:border-zinc-800">
            <Field label="Revision">
              <input
                type="number"
                value={revision}
                min={0}
                onChange={(e) => setRevision(Number(e.target.value) || 0)}
                className={inputCls}
              />
            </Field>
            <Field label="용도" required>
              <input
                type="text"
                value={purpose}
                onChange={(e) => setPurpose(e.target.value)}
                placeholder="예: 허가용 / 실시설계 / 착공용"
                className={inputCls}
              />
            </Field>
            <label className="mt-5 flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={withSafetyCert}
                onChange={(e) => setWithSafetyCert(e.target.checked)}
              />
              구조안전확인서 포함
            </label>
          </div>
        )}

        {sealType === "구조안전확인서" && (
          <Field label="용도" required>
            <input
              type="text"
              value={purpose}
              onChange={(e) => setPurpose(e.target.value)}
              placeholder="예: 허가용 / 실시설계 / 착공용"
              className={inputCls}
            />
          </Field>
        )}

        {sealType === "구조검토서" && (
          <Field label="내용요약">
            <textarea
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              rows={3}
              placeholder="검토 의견 요약"
              className={`${inputCls} resize-y`}
            />
          </Field>
        )}

        {sealType === "구조도면" && (
          <Field label="용도" required>
            <input
              type="text"
              value={purpose}
              onChange={(e) => setPurpose(e.target.value)}
              placeholder="예: 허가용 / 실시설계 / 착공용"
              className={inputCls}
            />
          </Field>
        )}

        {sealType === "기타" && (
          <Field label="문서종류" required>
            <input
              type="text"
              value={docKind}
              onChange={(e) => setDocKind(e.target.value)}
              placeholder="예: 공사관리계획"
              className={inputCls}
            />
          </Field>
        )}

        <Field label="제목 (생략 시 자동 생성)">
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={titlePreview}
            className={inputCls}
          />
          <p className="mt-0.5 text-[10px] text-zinc-400">
            미리보기: <span className="font-mono">{titlePreview}</span>
          </p>
        </Field>

        <Field label="비고">
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={2}
            className={`${inputCls} resize-y`}
          />
        </Field>

        <Field label="첨부파일 (선택, 다중 가능, 파일당 ≤200MB)">
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
