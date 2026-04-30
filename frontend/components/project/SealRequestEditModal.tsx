"use client";

import { useRef, useState } from "react";

import Modal from "@/components/ui/Modal";
import {
  addSealAttachments,
  getSealAttachmentUrl,
  updateSealRequest,
  type SealRequestItem,
} from "@/lib/api";

interface Props {
  item: SealRequestItem;
  onClose: () => void;
  onSaved: () => void;
}

/**
 * 재요청 / 입력 수정 모달.
 *
 * docs/request.md: "이전에 기입된 내용이 그대로 나타남(수정가능)" — 텍스트 필드는
 * prefill하고, 기존 첨부도 목록으로 보여주며 추가 업로드 가능.
 * 검토구분(seal_type)은 변경 불가 — 재등록이 필요하면 취소 후 새로 작성.
 */
export default function SealRequestEditModal({ item, onClose, onSaved }: Props) {
  const [title, setTitle] = useState(item.title);
  const [dueDate, setDueDate] = useState(item.due_date ?? "");
  const [realSource, setRealSource] = useState(item.real_source);
  const [purpose, setPurpose] = useState(item.purpose);
  const [revision, setRevision] = useState(item.revision ?? 0);
  const [withSafetyCert, setWithSafetyCert] = useState(item.with_safety_cert);
  const [summary, setSummary] = useState(item.summary);
  const [docKind, setDocKind] = useState(item.doc_kind);
  const [note, setNote] = useState(item.note);
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const onPickFiles = (list: FileList | null): void => {
    if (!list) return;
    const MAX = 200 * 1024 * 1024;
    const all = Array.from(list);
    const tooBig = all.filter((f) => f.size > MAX);
    if (tooBig.length > 0) {
      alert(
        `200MB 초과:\n${tooBig
          .map((f) => `• ${f.name} (${Math.round(f.size / 1024 / 1024)}MB)`)
          .join("\n")}`,
      );
    }
    const ok = all.filter((f) => f.size <= MAX);
    if (ok.length > 0) setPendingFiles((prev) => [...prev, ...ok]);
    if (fileInput.current) fileInput.current.value = "";
  };

  const submit = async (): Promise<void> => {
    if (!dueDate) {
      setErr("제출 예정일은 필수입니다");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await updateSealRequest(item.id, {
        title,
        due_date: dueDate,
        real_source: realSource,
        purpose,
        revision,
        with_safety_cert: withSafetyCert,
        summary,
        doc_kind: docKind,
        note,
      });
      // 첨부 추가가 있으면 같이 업로드 (상태가 자동으로 1차검토 중으로 복구)
      if (pendingFiles.length > 0) {
        await addSealAttachments(item.id, pendingFiles);
      }
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "저장 실패");
    } finally {
      setBusy(false);
    }
  };

  const isCalc = item.seal_type === "구조계산서";
  const needPurpose =
    item.seal_type === "구조계산서" ||
    item.seal_type === "구조안전확인서" ||
    item.seal_type === "구조도면";
  const isReview = item.seal_type === "구조검토서";
  const isEtc = item.seal_type === "기타";

  return (
    <Modal open onClose={onClose} title={`수정 / 재요청 — ${item.seal_type}`} size="md">
      <div className="space-y-3">
        <Field label="검토구분">
          <p className="rounded-md border border-zinc-200 bg-zinc-50 px-2.5 py-1.5 text-sm dark:border-zinc-800 dark:bg-zinc-900">
            {item.seal_type}
            {item.doc_no && (
              <span className="ml-2 text-zinc-500">({item.doc_no})</span>
            )}
          </p>
        </Field>

        <Field label="제출 예정일" required>
          <input
            type="date"
            value={dueDate}
            onChange={(e) => setDueDate(e.target.value)}
            className={inputCls}
          />
        </Field>

        <Field label="실제출처 (발주처와 다른 경우만)">
          <input
            type="text"
            value={realSource}
            onChange={(e) => setRealSource(e.target.value)}
            className={inputCls}
          />
        </Field>

        {isCalc && (
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
            <Field label="용도">
              <input
                type="text"
                value={purpose}
                onChange={(e) => setPurpose(e.target.value)}
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

        {needPurpose && !isCalc && (
          <Field label="용도">
            <input
              type="text"
              value={purpose}
              onChange={(e) => setPurpose(e.target.value)}
              className={inputCls}
            />
          </Field>
        )}

        {isReview && (
          <Field label="내용요약">
            <textarea
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              rows={3}
              className={`${inputCls} resize-y`}
            />
          </Field>
        )}

        {isEtc && (
          <Field label="문서종류">
            <input
              type="text"
              value={docKind}
              onChange={(e) => setDocKind(e.target.value)}
              className={inputCls}
            />
          </Field>
        )}

        <Field label="제목">
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
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

        <Field label={`기존 첨부 (${item.attachments.length})`}>
          {item.attachments.length === 0 ? (
            <p className="text-xs text-zinc-400">첨부 없음</p>
          ) : (
            <ul className="space-y-1">
              {item.attachments.map((f, i) => (
                <li
                  key={i}
                  className="flex items-center gap-2 rounded border border-zinc-200 px-2 py-1 text-xs dark:border-zinc-800"
                >
                  <span className="flex-1 truncate" title={f.name}>
                    📎 {f.name}
                    {f.size ? (
                      <span className="ml-1 text-zinc-400">
                        ({Math.round(f.size / 1024)} KB)
                      </span>
                    ) : null}
                  </span>
                  <button
                    type="button"
                    onClick={async () => {
                      try {
                        const r = await getSealAttachmentUrl(item.id, i);
                        const a = document.createElement("a");
                        a.href = r.url;
                        a.download = r.name;
                        a.click();
                      } catch (e) {
                        alert(
                          e instanceof Error ? e.message : "다운로드 실패",
                        );
                      }
                    }}
                    className="rounded border border-zinc-200 px-1.5 py-0.5 text-[10px] text-zinc-500 hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-800"
                  >
                    ↓
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Field>

        <Field label="첨부 추가 (선택, 다중 가능, 파일당 ≤200MB)">
          <input
            ref={fileInput}
            type="file"
            multiple
            onChange={(e) => onPickFiles(e.target.files)}
            className="block w-full text-xs file:mr-2 file:rounded-md file:border-0 file:bg-zinc-100 file:px-3 file:py-1.5 file:text-xs hover:file:bg-zinc-200 dark:file:bg-zinc-800 dark:file:text-zinc-100"
          />
          {pendingFiles.length > 0 && (
            <ul className="mt-2 space-y-1 text-xs">
              {pendingFiles.map((f, i) => (
                <li
                  key={i}
                  className="flex items-center justify-between rounded border border-amber-300 px-2 py-1 dark:border-amber-700"
                >
                  <span className="truncate" title={f.name}>
                    🆕 {f.name}{" "}
                    <span className="text-zinc-400">
                      ({Math.round(f.size / 1024)} KB)
                    </span>
                  </span>
                  <button
                    type="button"
                    onClick={() =>
                      setPendingFiles((prev) =>
                        prev.filter((_, j) => j !== i),
                      )
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
            className="rounded-md bg-amber-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-600 disabled:opacity-50"
          >
            {busy ? "저장 중..." : item.status === "반려" ? "재요청" : "저장"}
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
