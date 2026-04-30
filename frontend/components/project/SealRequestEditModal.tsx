"use client";

import { useState } from "react";

import Modal from "@/components/ui/Modal";
import { updateSealRequest, type SealRequestItem } from "@/lib/api";

interface Props {
  item: SealRequestItem;
  onClose: () => void;
  onSaved: () => void;
}

/**
 * 재요청 / 입력 수정 모달.
 *
 * - 반려된 요청을 보완해 다시 제출하거나, 1차검토 중 상태에서 입력값을 수정할 때 사용.
 * - 첨부 파일 추가는 별도 입력(상위 컴포넌트의 reupload input)을 사용.
 * - 검토구분(seal_type)은 변경 불가 — 재등록이 필요하면 취소 후 새로 작성.
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
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

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
