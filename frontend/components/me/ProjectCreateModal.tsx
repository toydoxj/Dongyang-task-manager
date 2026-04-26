"use client";

import { useState } from "react";

import Modal from "@/components/ui/Modal";
import { createProject } from "@/lib/api";
import { TEAMS, WORK_TYPES } from "@/lib/domain";
import { useClients } from "@/lib/hooks";

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}

export default function ProjectCreateModal({
  open,
  onClose,
  onCreated,
}: Props) {
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [client, setClient] = useState("");
  const [team, setTeam] = useState<string>("");
  const [workType, setWorkType] = useState<string>("");
  const [startDate, setStartDate] = useState("");
  const [contractStart, setContractStart] = useState("");
  const [contractEnd, setContractEnd] = useState("");
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 협력업체 목록 (모달 열릴 때만 fetch)
  const { data: clientData } = useClients(open);
  const clientMatch = clientData?.items.find(
    (c) => c.name.trim() === client.trim() && client.trim() !== "",
  );

  const reset = (): void => {
    setName("");
    setCode("");
    setClient("");
    setTeam("");
    setWorkType("");
    setStartDate("");
    setContractStart("");
    setContractEnd("");
    setAmount("");
    setError(null);
  };

  const submit = async (): Promise<void> => {
    if (!name.trim()) {
      setError("프로젝트명을 입력하세요");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const trimmedClient = client.trim();
      await createProject({
        name: name.trim(),
        code: code.trim() || undefined,
        // 협력업체 매칭되면 relation 으로, 아니면 text fallback
        client_relation_ids: clientMatch ? [clientMatch.id] : undefined,
        client_text: clientMatch ? undefined : trimmedClient || undefined,
        teams: team ? [team] : [],
        work_types: workType ? [workType] : [],
        start_date: startDate || undefined,
        contract_start: contractStart || undefined,
        contract_end: contractEnd || undefined,
        contract_amount: amount ? Number(amount) : undefined,
      });
      reset();
      onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "생성 실패");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="새 프로젝트 생성" size="lg">
      <div className="space-y-3">
        <p className="text-xs text-zinc-500">
          노션 메인 DB에 새 프로젝트 페이지를 생성합니다. 본인이 자동으로
          담당자에 추가됩니다.
        </p>

        <Field label="프로젝트명" required>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={inputCls}
            placeholder="OO 신축공사 구조설계"
            autoFocus
          />
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Sub CODE">
            <input
              type="text"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className={inputCls}
              placeholder="J260501"
            />
          </Field>
          <Field label="발주처">
            <input
              type="text"
              list="dy-clients"
              value={client}
              onChange={(e) => setClient(e.target.value)}
              className={inputCls}
              placeholder={
                clientData
                  ? `목록 ${clientData.count}개 자동완성, 없으면 직접 입력`
                  : "협력업체 목록 불러오는 중..."
              }
            />
            <datalist id="dy-clients">
              {clientData?.items.map((c) => (
                <option key={c.id} value={c.name}>
                  {c.category}
                </option>
              ))}
            </datalist>
            {client.trim() && (
              <p className="mt-1 text-[10px] text-zinc-500">
                {clientMatch
                  ? `✓ 매칭: ${clientMatch.name} (${clientMatch.category || "분류 없음"})`
                  : "신규 발주처로 입력 (text 컬럼)"}
              </p>
            )}
          </Field>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Field label="담당팀">
            <select
              value={team}
              onChange={(e) => setTeam(e.target.value)}
              className={inputCls}
            >
              <option value="">—</option>
              {TEAMS.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </Field>
          <Field label="업무내용">
            <select
              value={workType}
              onChange={(e) => setWorkType(e.target.value)}
              className={inputCls}
            >
              <option value="">—</option>
              {WORK_TYPES.map((w) => (
                <option key={w} value={w}>
                  {w}
                </option>
              ))}
            </select>
          </Field>
        </div>

        <Field label="수주일">
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className={inputCls}
          />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="계약 시작">
            <input
              type="date"
              value={contractStart}
              onChange={(e) => setContractStart(e.target.value)}
              className={inputCls}
            />
          </Field>
          <Field label="계약 완료">
            <input
              type="date"
              value={contractEnd}
              onChange={(e) => setContractEnd(e.target.value)}
              className={inputCls}
            />
          </Field>
        </div>

        <Field label="용역비 (원, VAT 제외)">
          <input
            type="number"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            className={inputCls}
            placeholder="1500000"
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
