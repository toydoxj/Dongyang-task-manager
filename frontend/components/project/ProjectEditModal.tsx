"use client";

import { useState } from "react";

import Modal from "@/components/ui/Modal";
import { updateProject } from "@/lib/api";
import type { Project } from "@/lib/domain";
import { PROJECT_STAGES, TEAMS, WORK_TYPES } from "@/lib/domain";
import { useClients } from "@/lib/hooks";

interface Props {
  project: Project | null;
  onClose: () => void;
  onSaved: () => void;
}

export default function ProjectEditModal({ project, onClose, onSaved }: Props) {
  if (!project) return null;
  return <Form key={project.id} project={project} onClose={onClose} onSaved={onSaved} />;
}

function Form({
  project,
  onClose,
  onSaved,
}: {
  project: Project;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(project.name);
  const [code, setCode] = useState(project.code);
  const [client, setClient] = useState(
    project.client_names[0] ?? project.client_text,
  );
  const [stage, setStage] = useState(project.stage);
  const [team, setTeam] = useState(project.teams[0] ?? "");
  const [workType, setWorkType] = useState(project.work_types[0] ?? "");
  const [startDate, setStartDate] = useState(project.start_date ?? "");
  const [contractStart, setContractStart] = useState(project.contract_start ?? "");
  const [contractEnd, setContractEnd] = useState(project.contract_end ?? "");
  const [amount, setAmount] = useState(
    project.contract_amount != null ? String(project.contract_amount) : "",
  );
  const [vat, setVat] = useState(project.vat != null ? String(project.vat) : "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: clientData } = useClients(true);
  const clientMatch = clientData?.items.find(
    (c) => c.name.trim() === client.trim() && client.trim() !== "",
  );

  const submit = async (): Promise<void> => {
    if (!name.trim()) {
      setError("프로젝트명을 입력하세요");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const trimmedClient = client.trim();
      const wasClient =
        project.client_names[0] ?? project.client_text ?? "";
      const clientChanged = trimmedClient !== wasClient;
      await updateProject(project.id, {
        name: name === project.name ? undefined : name.trim(),
        code: code === project.code ? undefined : code.trim(),
        // 협력업체 매칭 → relation, 아니면 text. 변경된 경우만 전송
        ...(clientChanged
          ? clientMatch
            ? { client_relation_ids: [clientMatch.id], client_text: "" }
            : { client_text: trimmedClient, client_relation_ids: [] }
          : {}),
        stage: stage === project.stage ? undefined : stage,
        teams:
          team === (project.teams[0] ?? "")
            ? undefined
            : team
              ? [team]
              : [],
        work_types:
          workType === (project.work_types[0] ?? "")
            ? undefined
            : workType
              ? [workType]
              : [],
        start_date:
          startDate === (project.start_date ?? "") ? undefined : startDate,
        contract_start:
          contractStart === (project.contract_start ?? "")
            ? undefined
            : contractStart,
        contract_end:
          contractEnd === (project.contract_end ?? "") ? undefined : contractEnd,
        contract_amount:
          (amount === "" ? null : Number(amount)) === project.contract_amount
            ? undefined
            : amount === ""
              ? undefined
              : Number(amount),
        vat:
          (vat === "" ? null : Number(vat)) === project.vat
            ? undefined
            : vat === ""
              ? undefined
              : Number(vat),
      });
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "저장 실패");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={true} onClose={onClose} title="프로젝트 편집" size="lg">
      <div className="space-y-3">
        <Field label="프로젝트명" required>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={inputCls}
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
            />
          </Field>
          <Field label="발주처">
            <input
              type="text"
              list="dy-clients-edit"
              value={client}
              onChange={(e) => setClient(e.target.value)}
              className={inputCls}
            />
            <datalist id="dy-clients-edit">
              {clientData?.items.map((c) => (
                <option key={c.id} value={c.name}>
                  {c.category}
                </option>
              ))}
            </datalist>
          </Field>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <Field label="진행단계">
            <select
              value={stage}
              onChange={(e) => setStage(e.target.value)}
              className={inputCls}
            >
              {PROJECT_STAGES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </Field>
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

        <div className="grid grid-cols-2 gap-3">
          <Field label="용역비 (VAT 제외)">
            <input
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className={inputCls}
            />
          </Field>
          <Field label="VAT">
            <input
              type="number"
              value={vat}
              onChange={(e) => setVat(e.target.value)}
              className={inputCls}
            />
          </Field>
        </div>

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
            {busy ? "저장 중..." : "저장"}
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
