"use client";

/**
 * 계약서 신규 생성 모달 — PR-FH/2.
 * 프로젝트 선택 + 메타 입력. 파일 업로드는 생성 후 상세 drawer에서 별도 수행.
 */

import { useState } from "react";

import { Field, inputCls } from "@/components/project/_shared";
import Modal from "@/components/ui/Modal";
import { createContract } from "@/lib/api";
import type { Project } from "@/lib/domain";

interface Props {
  open: boolean;
  projects: Project[];
  onClose: () => void;
  onCreated: () => void;
}

export default function ContractCreateModal({
  open,
  projects,
  onClose,
  onCreated,
}: Props) {
  const [projectId, setProjectId] = useState("");
  const [title, setTitle] = useState("원계약서");
  const [signedDate, setSignedDate] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [amount, setAmount] = useState<string>("");
  const [vatIncluded, setVatIncluded] = useState(false);
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = (): void => {
    setProjectId("");
    setTitle("원계약서");
    setSignedDate("");
    setStartDate("");
    setEndDate("");
    setAmount("");
    setVatIncluded(false);
    setNote("");
    setError(null);
  };

  const handleClose = (): void => {
    if (submitting) return;
    reset();
    onClose();
  };

  const handleSubmit = async (e: React.FormEvent): Promise<void> => {
    e.preventDefault();
    if (!projectId) {
      setError("프로젝트를 선택해주세요");
      return;
    }
    if (!title.trim()) {
      setError("계약서명을 입력해주세요");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await createContract({
        project_id: projectId,
        title: title.trim(),
        signed_date: signedDate || null,
        start_date: startDate || null,
        end_date: endDate || null,
        amount: amount ? parseInt(amount, 10) : null,
        vat_included: vatIncluded,
        note: note.trim(),
      });
      reset();
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal open={open} onClose={handleClose} title="새 계약서 등록" size="lg">
      <form onSubmit={handleSubmit} className="space-y-3">
        <Field label="프로젝트" required>
          <select
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            className={inputCls}
          >
            <option value="">— 선택 —</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.code ? `[${p.code}] ` : ""}
                {p.name || "(이름 없음)"}
              </option>
            ))}
          </select>
        </Field>
        <Field label="계약서명" required>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="예: 원계약서, 1차 변경계약서"
            className={inputCls}
          />
        </Field>
        <div className="grid grid-cols-3 gap-3">
          <Field label="체결일">
            <input
              type="date"
              value={signedDate}
              onChange={(e) => setSignedDate(e.target.value)}
              className={inputCls}
            />
          </Field>
          <Field label="계약 시작일">
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className={inputCls}
            />
          </Field>
          <Field label="계약 종료일">
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className={inputCls}
            />
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="계약금액 (원)">
            <input
              type="number"
              min={0}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="50000000"
              className={inputCls}
            />
          </Field>
          <label className="flex items-end gap-2 pb-1.5">
            <input
              type="checkbox"
              checked={vatIncluded}
              onChange={(e) => setVatIncluded(e.target.checked)}
            />
            <span className="text-xs text-zinc-700 dark:text-zinc-300">
              VAT 포함 금액
            </span>
          </label>
        </div>
        <Field label="메모">
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={2}
            className={inputCls}
          />
        </Field>
        {error && (
          <p className="rounded-md border border-red-500/40 bg-red-500/5 px-3 py-2 text-xs text-red-500">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={handleClose}
            disabled={submitting}
            className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
          >
            취소
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
          >
            {submitting ? "등록 중…" : "등록"}
          </button>
        </div>
        <p className="text-[10px] text-zinc-500">
          PDF 파일은 등록 후 상세에서 업로드합니다.
        </p>
      </form>
    </Modal>
  );
}
