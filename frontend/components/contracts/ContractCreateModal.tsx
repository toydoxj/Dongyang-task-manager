"use client";

/**
 * 계약서 신규 생성 모달 — PR-FH/2 / PR-FI/2 (프로젝트 typeahead) / PR-FI/5 (발주처·금액 경고).
 *
 * 프로젝트 선택 시 그 프로젝트의 발주처·계약금액을 자동 prefill.
 * 사용자가 다른 발주처/금액을 입력하면 amber 경고 + 「프로젝트도 업데이트」 옵션.
 */

import { useMemo, useState } from "react";

import EnsureProjectFolderButton from "@/components/common/EnsureProjectFolderButton";
import { Field, inputCls } from "@/components/project/_shared";
import Modal from "@/components/ui/Modal";
import { createContract, updateProject } from "@/lib/api";
import type { Client, Project } from "@/lib/domain";
import { useClients, useContracts } from "@/lib/hooks";
import { cn } from "@/lib/utils";

interface Props {
  open: boolean;
  projects: Project[];
  /** PR-FI/6: 「계약체크 + 미등록」 가상 row 클릭 시 prefill용. */
  initialProjectId?: string;
  onClose: () => void;
  onCreated: () => void;
}

export default function ContractCreateModal({
  open,
  projects,
  initialProjectId,
  onClose,
  onCreated,
}: Props) {
  // initial이 있으면 그것의 client/amount까지 prefill — handleSelectProject와 동일 로직.
  const initialProject = initialProjectId
    ? projects.find((p) => p.id === initialProjectId) ?? null
    : null;
  const [projectId, setProjectId] = useState(initialProjectId ?? "");
  // initial state는 prop 기준으로 한 번만 — Modal key remount로 새로 mount 시 재설정.
  const [clientId, setClientId] = useState(
    initialProject?.client_relation_ids?.[0] ?? "",
  );
  const [title, setTitle] = useState("원계약서");
  const [signedDate, setSignedDate] = useState("");
  // PR-FI/6 fix: 프로젝트 계약기간(contract_start/end)도 prefill — 가상 row에서 등록 시 자주 사용.
  const [startDate, setStartDate] = useState(initialProject?.contract_start ?? "");
  const [endDate, setEndDate] = useState(initialProject?.contract_end ?? "");
  const [amount, setAmount] = useState<string>(
    initialProject?.contract_amount != null
      ? String(initialProject.contract_amount)
      : "",
  );
  const [vatIncluded, setVatIncluded] = useState(false);
  const [note, setNote] = useState("");
  const [updateProjectClient, setUpdateProjectClient] = useState(false);
  const [updateProjectAmount, setUpdateProjectAmount] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: clientsData } = useClients(open);
  // PR-FK (사용자 요청): 같은 프로젝트에 이미 등록된 계약서 수 알림.
  // 차단은 안 함 — 변경계약/부속합의 등 다중 계약서 등록은 정상 케이스.
  const { data: existingContractsData } = useContracts(
    projectId ? { project_id: projectId } : undefined,
    open && !!projectId,
  );
  const existingCount = existingContractsData?.items.length ?? 0;

  const selectedProject = useMemo(
    () => (projectId ? projects.find((p) => p.id === projectId) ?? null : null),
    [projectId, projects],
  );

  const projectClientId = selectedProject?.client_relation_ids?.[0] ?? "";
  const projectAmount = selectedProject?.contract_amount ?? null;

  // PR-FI/5: 프로젝트 선택 변경 시 발주처/금액 자동 prefill. effect 대신 onChange
  // handler에서 직접 set — set-state-in-effect lint 회피 (사용자 정책).
  const handleSelectProject = (id: string): void => {
    setProjectId(id);
    setUpdateProjectClient(false);
    setUpdateProjectAmount(false);
    if (!id) {
      setClientId("");
      setAmount("");
      setStartDate("");
      setEndDate("");
      return;
    }
    const p = projects.find((x) => x.id === id);
    if (!p) return;
    setClientId(p.client_relation_ids?.[0] ?? "");
    setAmount(p.contract_amount != null ? String(p.contract_amount) : "");
    // PR-FI/6 fix: 프로젝트 계약기간도 prefill (수동 변경 가능).
    setStartDate(p.contract_start ?? "");
    setEndDate(p.contract_end ?? "");
  };

  const reset = (): void => {
    setProjectId("");
    setClientId("");
    setTitle("원계약서");
    setSignedDate("");
    setStartDate("");
    setEndDate("");
    setAmount("");
    setVatIncluded(false);
    setNote("");
    setUpdateProjectClient(false);
    setUpdateProjectAmount(false);
    setError(null);
  };

  const handleClose = (): void => {
    if (submitting) return;
    reset();
    onClose();
  };

  // 발주처 다름 검증 — 사용자가 명시 선택 후 차이가 있을 때만 경고.
  const clientDiffers = !!(
    selectedProject && clientId && projectClientId && clientId !== projectClientId
  );
  const amountNum = amount ? parseInt(amount, 10) : null;
  const amountDiffers = !!(
    selectedProject &&
    amountNum != null &&
    projectAmount != null &&
    amountNum !== projectAmount
  );

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
        client_id: clientId || null,
        title: title.trim(),
        signed_date: signedDate || null,
        start_date: startDate || null,
        end_date: endDate || null,
        amount: amountNum,
        vat_included: vatIncluded,
        note: note.trim(),
      });

      // PR-FI/5: 사용자가 체크한 경우 프로젝트 발주처/금액도 즉시 update.
      const projectPatch: { client_relation_ids?: string[]; contract_amount?: number } = {};
      if (updateProjectClient && clientDiffers && clientId) {
        projectPatch.client_relation_ids = [clientId];
      }
      if (updateProjectAmount && amountDiffers && amountNum != null) {
        projectPatch.contract_amount = amountNum;
      }
      if (Object.keys(projectPatch).length > 0) {
        try {
          await updateProject(projectId, projectPatch);
        } catch (err) {
          // contract 저장은 이미 성공 — 프로젝트 update 실패는 경고만.
          console.warn("프로젝트 update 실패:", err);
        }
      }

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
          <ProjectSearchSelect
            projects={projects}
            value={projectId}
            onChange={handleSelectProject}
          />
          {existingCount > 0 && (
            <p className="mt-1 rounded-md border border-blue-500/40 bg-blue-500/5 px-3 py-2 text-xs text-blue-700 dark:text-blue-300">
              ℹ 이 프로젝트에 이미 <b>{existingCount}건</b>의 계약서가 등록되어
              있습니다. 변경계약·부속합의면 그대로 진행하세요.
            </p>
          )}
          {/* PR-FV: 선택된 프로젝트의 WORKS Drive 폴더가 없으면 만들기 버튼 노출 */}
          <EnsureProjectFolderButton project={selectedProject} />
        </Field>
        <Field label="발주처">
          <ClientSearchSelect
            clients={clientsData?.items ?? []}
            value={clientId}
            onChange={setClientId}
            placeholder={
              projectClientId
                ? "프로젝트 발주처 자동 적용됨 — 다른 발주처 선택 가능"
                : "발주처 검색…"
            }
          />
          {clientDiffers && (
            <ProjectDiffWarning
              text={`프로젝트 발주처와 다릅니다 (현재: ${
                clientsData?.items.find((c) => c.id === projectClientId)?.name ?? "—"
              })`}
              checked={updateProjectClient}
              onToggle={() => setUpdateProjectClient((v) => !v)}
              confirmLabel="이 계약서 발주처로 프로젝트도 업데이트"
            />
          )}
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
        {amountDiffers && (
          <ProjectDiffWarning
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

/** PR-FI/2: 프로젝트 검색 typeahead. */
function ProjectSearchSelect({
  projects,
  value,
  onChange,
}: {
  projects: Project[];
  value: string;
  onChange: (id: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [focused, setFocused] = useState(false);

  const selected = useMemo(
    () => (value ? projects.find((p) => p.id === value) : null),
    [value, projects],
  );

  const display = selected
    ? `${selected.code ? `[${selected.code}] ` : ""}${selected.name || "(이름 없음)"}`
    : query;

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return projects.slice(0, 30);
    return projects
      .filter((p) => {
        const haystack = `${p.code ?? ""} ${p.name ?? ""}`.toLowerCase();
        return haystack.includes(q);
      })
      .slice(0, 30);
  }, [projects, query]);

  return (
    <div className="relative">
      <div className="relative">
        <input
          type="text"
          value={display}
          onChange={(e) => {
            if (selected) onChange("");
            setQuery(e.target.value);
          }}
          onFocus={() => setFocused(true)}
          onBlur={() => setTimeout(() => setFocused(false), 150)}
          placeholder="CODE 또는 프로젝트명으로 검색…"
          className={cn(inputCls, selected && "pr-8")}
        />
        {selected && (
          <button
            type="button"
            onClick={() => {
              onChange("");
              setQuery("");
            }}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200"
            aria-label="선택 해제"
          >
            ✕
          </button>
        )}
      </div>
      {focused && !selected && filtered.length > 0 && (
        <ul className="absolute left-0 right-0 top-full z-10 mt-1 max-h-64 overflow-y-auto rounded-md border border-zinc-200 bg-white shadow-lg dark:border-zinc-700 dark:bg-zinc-900">
          {filtered.map((p) => (
            <li key={p.id}>
              <button
                type="button"
                onMouseDown={(e) => {
                  e.preventDefault();
                  onChange(p.id);
                  setQuery("");
                  setFocused(false);
                }}
                className="block w-full px-3 py-1.5 text-left text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800"
              >
                <span className="font-mono text-[11px] text-zinc-500">
                  {p.code || "—"}
                </span>{" "}
                {p.name || "(이름 없음)"}
              </button>
            </li>
          ))}
        </ul>
      )}
      {focused && !selected && filtered.length === 0 && query && (
        <div className="absolute left-0 right-0 top-full z-10 mt-1 rounded-md border border-zinc-200 bg-white px-3 py-2 text-xs text-zinc-500 shadow-lg dark:border-zinc-700 dark:bg-zinc-900">
          검색 결과가 없습니다.
        </div>
      )}
    </div>
  );
}

/** PR-FI/5: 발주처 검색 typeahead. ProjectSearchSelect와 유사한 패턴. */
export function ClientSearchSelect({
  clients,
  value,
  onChange,
  placeholder,
}: {
  clients: Client[];
  value: string;
  onChange: (id: string) => void;
  placeholder?: string;
}) {
  const [query, setQuery] = useState("");
  const [focused, setFocused] = useState(false);

  const selected = useMemo(
    () => (value ? clients.find((c) => c.id === value) : null),
    [value, clients],
  );

  const display = selected ? selected.name : query;

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return clients.slice(0, 30);
    return clients
      .filter((c) => c.name.toLowerCase().includes(q))
      .slice(0, 30);
  }, [clients, query]);

  return (
    <div className="relative">
      <div className="relative">
        <input
          type="text"
          value={display}
          onChange={(e) => {
            if (selected) onChange("");
            setQuery(e.target.value);
          }}
          onFocus={() => setFocused(true)}
          onBlur={() => setTimeout(() => setFocused(false), 150)}
          placeholder={placeholder ?? "발주처 검색…"}
          className={cn(inputCls, selected && "pr-8")}
        />
        {selected && (
          <button
            type="button"
            onClick={() => {
              onChange("");
              setQuery("");
            }}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200"
            aria-label="선택 해제"
          >
            ✕
          </button>
        )}
      </div>
      {focused && !selected && filtered.length > 0 && (
        <ul className="absolute left-0 right-0 top-full z-10 mt-1 max-h-64 overflow-y-auto rounded-md border border-zinc-200 bg-white shadow-lg dark:border-zinc-700 dark:bg-zinc-900">
          {filtered.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                onMouseDown={(e) => {
                  e.preventDefault();
                  onChange(c.id);
                  setQuery("");
                  setFocused(false);
                }}
                className="block w-full px-3 py-1.5 text-left text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800"
              >
                {c.name}
              </button>
            </li>
          ))}
        </ul>
      )}
      {focused && !selected && filtered.length === 0 && query && (
        <div className="absolute left-0 right-0 top-full z-10 mt-1 rounded-md border border-zinc-200 bg-white px-3 py-2 text-xs text-zinc-500 shadow-lg dark:border-zinc-700 dark:bg-zinc-900">
          검색 결과가 없습니다.
        </div>
      )}
    </div>
  );
}

/** PR-FI/5: 프로젝트와 다를 때 amber 경고 + 「프로젝트도 업데이트」 체크박스. */
function ProjectDiffWarning({
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
