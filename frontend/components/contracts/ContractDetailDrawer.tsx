"use client";

/**
 * 계약서 상세 + 편집 drawer — PR-FH/2~3.
 *
 * 3개 sub-section (펼침 토글):
 *   1. 계약 메타 — PATCH (제목/날짜/금액/VAT/메모)
 *   2. 계약 분담 — 프로젝트 페이지로 link (별도 PR에서 ContractItemsEditor embed)
 *   3. 계약서 파일 — 다운로드 / 업로드 / 삭제
 */

import Link from "next/link";
import { useState } from "react";

import { Field, inputCls } from "@/components/project/_shared";
import Modal from "@/components/ui/Modal";
import {
  deleteContract,
  deleteContractFile,
  patchContract,
  uploadContractFile,
} from "@/lib/api";
import type { Contract } from "@/lib/domain";

interface Props {
  contract: Contract | null;
  onClose: () => void;
  onChanged: () => void;
}

const KRW = (n: number | null | undefined): string => {
  if (n == null) return "—";
  return n.toLocaleString("ko-KR") + "원";
};

export default function ContractDetailDrawer({
  contract,
  onClose,
  onChanged,
}: Props) {
  if (!contract) return null;
  return (
    <Modal
      open={true}
      onClose={onClose}
      title={`${contract.project_code ? `[${contract.project_code}] ` : ""}${contract.title}`}
      size="lg"
    >
      <Body contract={contract} onClose={onClose} onChanged={onChanged} />
    </Modal>
  );
}

function Body({
  contract,
  onClose,
  onChanged,
}: {
  contract: Contract;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [title, setTitle] = useState(contract.title);
  const [signedDate, setSignedDate] = useState(contract.signed_date ?? "");
  const [startDate, setStartDate] = useState(contract.start_date ?? "");
  const [endDate, setEndDate] = useState(contract.end_date ?? "");
  const [amount, setAmount] = useState<string>(
    contract.amount != null ? String(contract.amount) : "",
  );
  const [vatIncluded, setVatIncluded] = useState(contract.vat_included);
  const [note, setNote] = useState(contract.note);
  const [savingMeta, setSavingMeta] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 펼침/접힘 상태 — 메타 default 펼침, 분담/파일 default 접힘.
  const [openMeta, setOpenMeta] = useState(true);
  const [openItems, setOpenItems] = useState(false);
  const [openFile, setOpenFile] = useState(true);

  const handleSaveMeta = async (): Promise<void> => {
    setSavingMeta(true);
    setError(null);
    try {
      await patchContract(contract.id, {
        title: title.trim(),
        signed_date: signedDate || null,
        start_date: startDate || null,
        end_date: endDate || null,
        amount: amount ? parseInt(amount, 10) : null,
        vat_included: vatIncluded,
        note,
      });
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSavingMeta(false);
    }
  };

  const handleUpload = async (
    e: React.ChangeEvent<HTMLInputElement>,
  ): Promise<void> => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      await uploadContractFile(contract.id, file);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  };

  const handleDeleteFile = async (): Promise<void> => {
    if (!confirm("첨부된 파일을 삭제하시겠습니까?")) return;
    setBusy(true);
    setError(null);
    try {
      await deleteContractFile(contract.id);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteContract = async (): Promise<void> => {
    if (
      !confirm(
        `「${contract.title}」 계약서를 삭제하시겠습니까?\n첨부된 PDF도 함께 삭제됩니다.`,
      )
    )
      return;
    setBusy(true);
    setError(null);
    try {
      await deleteContract(contract.id);
      onChanged();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      {/* 헤더 — 프로젝트 정보 */}
      <div className="rounded-md bg-zinc-50 px-3 py-2 text-xs dark:bg-zinc-800/50">
        <div>
          <span className="text-zinc-500">프로젝트:</span>{" "}
          <Link
            href={`/projects/${contract.project_id}`}
            target="_blank"
            className="font-medium text-blue-600 hover:underline dark:text-blue-400"
          >
            {contract.project_name || "(이름 없음)"}
          </Link>
        </div>
        <div className="mt-0.5">
          <span className="text-zinc-500">발주처:</span>{" "}
          {contract.client_name || "—"}
        </div>
        <div className="mt-0.5">
          <span className="text-zinc-500">총 계약금액:</span>{" "}
          <span className="font-mono">{KRW(contract.amount)}</span>
          {contract.vat_included && (
            <span className="ml-1 text-amber-700">(VAT 포함)</span>
          )}
        </div>
      </div>

      {/* 1. 계약 메타 */}
      <Section
        label="계약 메타"
        open={openMeta}
        onToggle={() => setOpenMeta((v) => !v)}
      >
        <div className="space-y-3">
          <Field label="계약서명">
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
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
            <Field label="시작일">
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className={inputCls}
              />
            </Field>
            <Field label="종료일">
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
          <button
            type="button"
            onClick={handleSaveMeta}
            disabled={savingMeta}
            className="rounded-md bg-zinc-900 px-3 py-1.5 text-xs text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
          >
            {savingMeta ? "저장 중…" : "메타 저장"}
          </button>
        </div>
      </Section>

      {/* 2. 계약서 파일 */}
      <Section
        label="계약서 파일"
        open={openFile}
        onToggle={() => setOpenFile((v) => !v)}
      >
        <div className="space-y-2">
          {contract.drive_url ? (
            <div className="flex items-center justify-between rounded-md border border-zinc-200 bg-white p-2 text-xs dark:border-zinc-800 dark:bg-zinc-950">
              <div className="min-w-0">
                <a
                  href={contract.drive_url}
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium text-blue-600 hover:underline dark:text-blue-400"
                >
                  {contract.file_name || "(파일명 없음)"}
                </a>
                {contract.uploaded_at && (
                  <p className="mt-0.5 text-[10px] text-zinc-500">
                    업로드: {contract.uploaded_at.slice(0, 10)}
                  </p>
                )}
              </div>
              <button
                type="button"
                onClick={handleDeleteFile}
                disabled={busy}
                className="rounded border border-red-500/40 px-2 py-1 text-[11px] text-red-600 hover:bg-red-500/10 disabled:opacity-50"
              >
                파일 삭제
              </button>
            </div>
          ) : (
            <p className="text-xs text-zinc-500">첨부된 파일이 없습니다.</p>
          )}
          <label className="flex items-center gap-2">
            <input
              type="file"
              accept=".pdf,.doc,.docx,.hwp,.hwpx,application/pdf"
              onChange={handleUpload}
              disabled={busy}
              className="text-xs"
            />
            {busy && <span className="text-[11px] text-zinc-500">업로드 중…</span>}
          </label>
          <p className="text-[10px] text-zinc-500">
            허용 형식: PDF, DOC, DOCX, HWP, HWPX · 최대 30MB. 새 파일을
            업로드하면 기존 파일은 자동 교체됩니다.
          </p>
        </div>
      </Section>

      {/* 3. 계약 분담 — 프로젝트 상세 페이지에서 직접 편집 (controlled 패턴이라 embed 보류) */}
      <Section
        label="계약 분담 (공동수급 등)"
        open={openItems}
        onToggle={() => setOpenItems((v) => !v)}
      >
        <p className="text-xs text-zinc-600 dark:text-zinc-400">
          계약 분담(공동수급·추가용역) 편집은 프로젝트 상세 페이지에서
          진행합니다.
        </p>
        <Link
          href={`/projects/${contract.project_id}`}
          target="_blank"
          className="mt-2 inline-block rounded-md border border-zinc-300 px-3 py-1.5 text-xs hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
        >
          프로젝트 상세 열기 →
        </Link>
      </Section>

      {error && (
        <p className="rounded-md border border-red-500/40 bg-red-500/5 px-3 py-2 text-xs text-red-500">
          {error}
        </p>
      )}

      <div className="flex justify-between border-t border-zinc-200 pt-3 dark:border-zinc-800">
        <button
          type="button"
          onClick={handleDeleteContract}
          disabled={busy}
          className="rounded-md border border-red-500/40 px-3 py-1.5 text-xs text-red-600 hover:bg-red-500/10 disabled:opacity-50"
        >
          계약서 삭제
        </button>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
        >
          닫기
        </button>
      </div>
    </div>
  );
}

function Section({
  label,
  open,
  onToggle,
  children,
}: {
  label: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-md border border-zinc-200 dark:border-zinc-800">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-2 bg-zinc-50 px-3 py-2 text-left text-sm font-medium hover:bg-zinc-100 dark:bg-zinc-800/50 dark:hover:bg-zinc-800"
      >
        <span className="text-xs">{open ? "▼" : "▶"}</span>
        <span>{label}</span>
      </button>
      {open && (
        <div className="border-t border-zinc-200 p-3 dark:border-zinc-800">
          {children}
        </div>
      )}
    </section>
  );
}
