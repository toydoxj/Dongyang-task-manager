"use client";

/**
 * 계약서 상세 + 편집 drawer — PR-FH/2~3 / PR-FI/5 (발주처·금액 경고).
 *
 * 3개 sub-section (펼침 토글):
 *   1. 계약 메타 — PATCH (제목/발주처/날짜/금액/VAT/메모) + 프로젝트 다를 시 경고
 *   2. 계약 분담 — 프로젝트 페이지로 link
 *   3. 계약서 파일 — 다운로드 / 업로드 / 삭제
 */

import { useMemo, useState } from "react";

import { ProjectPopupLink } from "@/components/common/PopupLinks";

import EnsureProjectFolderButton from "@/components/common/EnsureProjectFolderButton";
import { ClientSearchSelect } from "@/components/contracts/ContractCreateModal";
import { Field, inputCls } from "@/components/project/_shared";
import Modal from "@/components/ui/Modal";
import {
  deleteContract,
  deleteContractFile,
  getContractDownloadUrl,
  patchContract,
  updateProject,
  uploadContractFile,
} from "@/lib/api";
import type { Contract } from "@/lib/domain";
import { useClients, useProject } from "@/lib/hooks";
import { cn } from "@/lib/utils";

interface Props {
  contract: Contract | null;
  onClose: () => void;
  /**
   * 변경 발생 시 호출. 갱신된 Contract 객체를 전달하면 caller가 selected
   * state를 즉시 update해 stale view 회피 가능 (PR-GA fix).
   */
  onChanged: (updated?: Contract) => void;
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
  onChanged: (updated?: Contract) => void;
}) {
  const [title, setTitle] = useState(contract.title);
  const [clientId, setClientId] = useState(contract.client_id ?? "");
  const [signedDate, setSignedDate] = useState(contract.signed_date ?? "");
  const [startDate, setStartDate] = useState(contract.start_date ?? "");
  const [endDate, setEndDate] = useState(contract.end_date ?? "");
  const [amount, setAmount] = useState<string>(
    contract.amount != null ? String(contract.amount) : "",
  );
  const [vatIncluded, setVatIncluded] = useState(contract.vat_included);
  const [note, setNote] = useState(contract.note);
  const [updateProjectClient, setUpdateProjectClient] = useState(false);
  const [updateProjectAmount, setUpdateProjectAmount] = useState(false);
  const [savingMeta, setSavingMeta] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // PR-FZ: 드래그 시 dropzone 시각 강조용.
  const [dragOver, setDragOver] = useState(false);

  // PR-FI/5: 프로젝트 발주처·계약금액과 다를 시 경고용.
  const { data: project } = useProject(contract.project_id);
  const { data: clientsData } = useClients(true);
  const projectClientId = project?.client_relation_ids?.[0] ?? "";
  const projectAmount = project?.contract_amount ?? null;
  const effectiveClientId = clientId || projectClientId;
  const clientDiffers = !!(
    effectiveClientId && projectClientId && effectiveClientId !== projectClientId
  );
  const amountNum = amount ? parseInt(amount, 10) : null;
  const amountDiffers = !!(
    amountNum != null && projectAmount != null && amountNum !== projectAmount
  );
  const projectClientName = useMemo(
    () =>
      clientsData?.items.find((c) => c.id === projectClientId)?.name ?? "—",
    [clientsData, projectClientId],
  );

  // 펼침/접힘 상태 — 메타 default 펼침, 분담/파일 default 접힘.
  const [openMeta, setOpenMeta] = useState(true);
  const [openItems, setOpenItems] = useState(false);
  const [openFile, setOpenFile] = useState(true);

  const handleSaveMeta = async (): Promise<void> => {
    setSavingMeta(true);
    setError(null);
    try {
      const updated = await patchContract(contract.id, {
        title: title.trim(),
        client_id: clientId || null,
        signed_date: signedDate || null,
        start_date: startDate || null,
        end_date: endDate || null,
        amount: amountNum,
        vat_included: vatIncluded,
        note,
      });
      // PR-FI/5: 사용자 체크 시 프로젝트도 즉시 update.
      const projectPatch: {
        client_relation_ids?: string[];
        contract_amount?: number;
      } = {};
      if (updateProjectClient && clientDiffers && effectiveClientId) {
        projectPatch.client_relation_ids = [effectiveClientId];
      }
      if (updateProjectAmount && amountDiffers && amountNum != null) {
        projectPatch.contract_amount = amountNum;
      }
      if (Object.keys(projectPatch).length > 0) {
        try {
          await updateProject(contract.project_id, projectPatch);
        } catch (err) {
          console.warn("프로젝트 update 실패:", err);
        }
      }
      setUpdateProjectClient(false);
      setUpdateProjectAmount(false);
      // PR-GD: 갱신된 contract 전달 — modal stale view 회피.
      onChanged(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSavingMeta(false);
    }
  };

  // PR-FZ: input change + drag&drop 공통 업로드 코어.
  // PR-GA: backend 응답으로 받은 갱신 Contract를 onChanged에 전달 — modal의
  // contract prop이 즉시 새 drive_url로 교체되도록 caller가 setSelected.
  const uploadFile = async (file: File): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      const updated = await uploadContractFile(contract.id, file);
      onChanged(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleUpload = async (
    e: React.ChangeEvent<HTMLInputElement>,
  ): Promise<void> => {
    const file = e.target.files?.[0];
    if (!file) return;
    await uploadFile(file);
    e.target.value = "";
  };

  // PR-FZ: 드래그 업로드 — dropzone 위에 파일 드롭 시 즉시 업로드.
  const handleDrop = async (
    e: React.DragEvent<HTMLLabelElement>,
  ): Promise<void> => {
    e.preventDefault();
    setDragOver(false);
    if (busy) return;
    const file = e.dataTransfer.files?.[0];
    if (!file) return;
    await uploadFile(file);
  };

  const handleDeleteFile = async (): Promise<void> => {
    if (!confirm("첨부된 파일을 삭제하시겠습니까?")) return;
    setBusy(true);
    setError(null);
    try {
      // PR-GD: deleteContractFile 응답으로 갱신 contract 받아 onChanged에 전달.
      // 이전엔 onChanged()만 호출해 list mutate는 됐지만 editing state는 stale →
      // modal에 「다운로드」 버튼이 그대로 보여 사용자가 새로고침해야 반영되는 회귀.
      const updated = await deleteContractFile(contract.id);
      onChanged(updated);
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
          <ProjectPopupLink
            id={contract.project_id}
            defaultStyle={false}
            className="font-medium text-blue-600 hover:underline dark:text-blue-400"
          >
            {contract.project_name || "(이름 없음)"}
          </ProjectPopupLink>
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
          <Field label="발주처">
            <ClientSearchSelect
              clients={clientsData?.items ?? []}
              value={clientId}
              onChange={setClientId}
              placeholder="프로젝트 발주처와 동일 시 비워두세요"
            />
            {clientDiffers && (
              <DiffWarning
                text={`프로젝트 발주처와 다릅니다 (현재: ${projectClientName})`}
                checked={updateProjectClient}
                onToggle={() => setUpdateProjectClient((v) => !v)}
                confirmLabel="이 계약서 발주처로 프로젝트도 업데이트"
              />
            )}
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
          {amountDiffers && (
            <DiffWarning
              text={`프로젝트 계약금액과 다릅니다 (현재: ${(projectAmount ?? 0).toLocaleString("ko-KR")}원)`}
              checked={updateProjectAmount}
              onToggle={() => setUpdateProjectAmount((v) => !v)}
              confirmLabel="이 계약서 금액으로 프로젝트도 업데이트"
            />
          )}
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
          {/* PR-FW: 프로젝트 폴더 없으면 업로드 전에 만들기 버튼 노출 */}
          <EnsureProjectFolderButton project={project} />
          {contract.drive_url ? (
            <div className="flex items-center justify-between rounded-md border border-zinc-200 bg-white p-2 text-xs dark:border-zinc-800 dark:bg-zinc-950">
              <div className="min-w-0">
                {/* PR-GE: 날인 패턴 — backend가 임시 signed URL 발급. drive_url 직접 클릭 시 NAVER Drive 권한 거부 회피. */}
                <button
                  type="button"
                  onClick={async () => {
                    try {
                      const r = await getContractDownloadUrl(contract.id);
                      const a = document.createElement("a");
                      a.href = r.url;
                      a.download = r.name;
                      a.click();
                    } catch (e) {
                      alert(e instanceof Error ? e.message : "다운로드 실패");
                    }
                  }}
                  className="font-medium text-blue-600 hover:underline dark:text-blue-400"
                >
                  {contract.file_name || "(파일명 없음)"}
                </button>
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
          {/* PR-FY: 시인성 강화 — 브라우저 기본 file input 대신 점선 dropzone 버튼. */}
          {/* PR-FZ: 드래그 앤 드롭 업로드 지원 (label 위에 파일 떨굼). */}
          <label
            onDragOver={(e) => {
              e.preventDefault();
              if (!busy) setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            className={cn(
              "flex cursor-pointer items-center justify-center gap-2 rounded-md border-2 border-dashed px-4 py-3 text-sm transition-colors",
              busy
                ? "cursor-wait border-zinc-300 bg-zinc-50 text-zinc-400 dark:border-zinc-700 dark:bg-zinc-900"
                : dragOver
                ? "border-blue-500 bg-blue-100 text-blue-800 dark:border-blue-400 dark:bg-blue-950/50 dark:text-blue-200"
                : "border-zinc-300 bg-zinc-50 text-zinc-700 hover:border-blue-400 hover:bg-blue-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:border-blue-500 dark:hover:bg-blue-950/30",
            )}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              className="h-4 w-4"
            >
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
            <span>
              {busy
                ? "업로드 중…"
                : dragOver
                ? "여기에 놓아 업로드"
                : contract.drive_url
                ? "클릭 또는 파일을 드래그해 업로드 (기존 파일 교체)"
                : "클릭 또는 파일을 드래그해 업로드"}
            </span>
            <input
              type="file"
              accept=".pdf,.doc,.docx,.hwp,.hwpx,application/pdf"
              onChange={handleUpload}
              disabled={busy}
              className="hidden"
            />
          </label>
          <p className="text-[10px] text-zinc-500">
            허용 형식: PDF, DOC, DOCX, HWP, HWPX · 최대 30MB.
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
        <ProjectPopupLink
          id={contract.project_id}
          defaultStyle={false}
          className="mt-2 inline-block rounded-md border border-zinc-300 px-3 py-1.5 text-xs hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
        >
          프로젝트 상세 열기 →
        </ProjectPopupLink>
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

function DiffWarning({
  text,
  checked,
  onToggle,
  confirmLabel,
}: {
  text: string;
  checked: boolean;
  onToggle: () => void;
  confirmLabel: string;
}) {
  return (
    <div className="mt-1 rounded-md border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-xs">
      <p className="text-amber-700 dark:text-amber-300">⚠ {text}</p>
      <label className="mt-1 flex items-center gap-2">
        <input type="checkbox" checked={checked} onChange={onToggle} />
        <span className="text-zinc-700 dark:text-zinc-300">{confirmLabel}</span>
      </label>
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
