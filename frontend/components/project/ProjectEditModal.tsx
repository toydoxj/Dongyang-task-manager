"use client";

import { useState } from "react";
import { useSWRConfig } from "swr";

import ContractItemsEditor, {
  type DraftContractItem,
  toDraft,
} from "@/components/project/ContractItemsEditor";
import Modal from "@/components/ui/Modal";
import MultiSelectChips from "@/components/ui/MultiSelectChips";
import {
  createClient,
  createContractItem,
  deleteContractItem,
  updateContractItem,
  updateProject,
} from "@/lib/api";
import type { ClientListResponse, Project } from "@/lib/domain";
import { PROJECT_STAGES } from "@/lib/domain";
import {
  keys,
  useClients,
  useContractItems,
  useProjectOptions,
} from "@/lib/hooks";

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
  // 발주처: relation 이름 우선, 없으면 임시 텍스트, 둘 다 없으면 빈 문자열로 controlled input 보장
  const [client, setClient] = useState<string>(
    project.client_names[0] ?? project.client_text ?? "",
  );
  const [stage, setStage] = useState(project.stage);
  const [assignees, setAssignees] = useState<string[]>(project.assignees);
  const [workTypes, setWorkTypes] = useState<string[]>(project.work_types);
  const [startDate, setStartDate] = useState(project.start_date ?? "");
  const [contractStart, setContractStart] = useState(project.contract_start ?? "");
  const [contractEnd, setContractEnd] = useState(project.contract_end ?? "");
  const [amount, setAmount] = useState(
    project.contract_amount != null ? String(project.contract_amount) : "",
  );
  const [vat, setVat] = useState(project.vat != null ? String(project.vat) : "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [clientAdding, setClientAdding] = useState(false);

  const { mutate } = useSWRConfig();
  const { data: clientData } = useClients(true);
  const { data: optionsData } = useProjectOptions(true);
  const { data: contractItemsData } = useContractItems(project.id);
  const workTypeOptions = optionsData?.work_types ?? [];

  // 분담 항목 — 서버 응답이 들어오면 초기 state로 채움 (lazy 초기화는 SWR이 처리)
  const [contractItems, setContractItems] = useState<DraftContractItem[]>([]);
  const [contractItemsInitialized, setContractItemsInitialized] = useState(false);
  if (contractItemsData && !contractItemsInitialized) {
    setContractItems(contractItemsData.items.map(toDraft));
    setContractItemsInitialized(true);
  }
  // 정규화 매칭 — 백엔드의 중복 판정과 동일하게 trim + lower 비교
  const norm = (s: string): string => s.trim().toLowerCase();
  const clientMatch =
    client.trim() === ""
      ? undefined
      : clientData?.items.find((c) => norm(c.name) === norm(client));
  const showAddClient = !clientMatch && client.trim() !== "" && !clientAdding;

  const addClientToDb = async (): Promise<void> => {
    const trimmed = client.trim();
    if (!trimmed) return;
    setClientAdding(true);
    setError(null);
    try {
      const created = await createClient({ name: trimmed });
      // race 회피: SWR 캐시에 즉시 주입 후 setClient. revalidate=false라
      // 다음 렌더에서 곧바로 clientMatch가 잡힘 → 저장 시 relation 보장.
      await mutate(
        keys.clients(),
        (current: ClientListResponse | undefined) => {
          if (!current) return current;
          if (current.items.some((c) => c.id === created.id)) return current;
          return {
            items: [...current.items, created],
            count: current.count + 1,
          };
        },
        { revalidate: false },
      );
      setClient(created.name);
    } catch (err) {
      setError(err instanceof Error ? err.message : "발주처 등록 실패");
    } finally {
      setClientAdding(false);
    }
  };

  const addContractClient = async (clientName: string): Promise<string> => {
    const created = await createClient({ name: clientName });
    await mutate(
      keys.clients(),
      (current: ClientListResponse | undefined) => {
        if (!current) return current;
        if (current.items.some((c) => c.id === created.id)) return current;
        return {
          items: [...current.items, created],
          count: current.count + 1,
        };
      },
      { revalidate: false },
    );
    return created.id;
  };

  const syncTotalsFromItems = (): void => {
    let amt = 0;
    let v = 0;
    for (const it of contractItems) {
      amt += it.amount || 0;
      v += it.vat || 0;
    }
    setAmount(String(amt));
    setVat(String(v));
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
      const wasClient =
        project.client_names[0] ?? project.client_text ?? "";
      const clientChanged = trimmedClient !== wasClient;
      // diff 기반 patch 빌드 — 빈 객체면 updateProject 호출 자체 skip (분담 항목만 변경한 경우)
      type Patch = Parameters<typeof updateProject>[1];
      const patch: Patch = {
        name: name === project.name ? undefined : name.trim(),
        code: code === project.code ? undefined : code.trim(),
        ...(clientChanged
          ? clientMatch
            ? { client_relation_ids: [clientMatch.id], client_text: "" }
            : { client_text: trimmedClient, client_relation_ids: [] }
          : {}),
        stage: stage === project.stage ? undefined : stage,
        assignees:
          arraysEqual(assignees, project.assignees) ? undefined : assignees,
        work_types:
          arraysEqual(workTypes, project.work_types) ? undefined : workTypes,
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
      };
      const hasProjectChange = Object.values(patch).some(
        (v) => v !== undefined,
      );
      if (hasProjectChange) {
        await updateProject(project.id, patch);
      }

      // 분담 항목 diff 처리 — 서버 원본과 비교해 create/update/delete
      if (contractItemsInitialized) {
        const original = contractItemsData?.items ?? [];
        const currentIds = new Set(
          contractItems.filter((c) => c.id).map((c) => c.id),
        );
        // delete: 원본에 있는데 current에 없는 것
        const toDelete = original.filter((o) => !currentIds.has(o.id));
        for (const o of toDelete) {
          // client_id가 비어있으면 미매칭이므로 발주처 등록 검증은 생략
          await deleteContractItem(o.id);
        }
        for (const it of contractItems) {
          if (!it.client_id) continue; // 미매칭 발주처는 skip (사용자에게 경고는 UI에서)
          if (!it.id) {
            await createContractItem({
              project_id: project.id,
              client_id: it.client_id,
              label: it.label,
              amount: it.amount,
              vat: it.vat,
              sort_order: it.sort_order,
            });
            continue;
          }
          if (it._origin === "modified") {
            await updateContractItem(it.id, {
              client_id: it.client_id,
              label: it.label,
              amount: it.amount,
              vat: it.vat,
              sort_order: it.sort_order,
            });
          }
        }
        // SWR 캐시 무효화 (수금 페이지가 contractItems를 사용하므로)
        await mutate(keys.contractItems(project.id));
      }

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
            {showAddClient && (
              <div className="mt-1 flex items-center gap-2">
                <p className="text-[10px] text-zinc-500">
                  미등록 발주처입니다 — 추가하지 않으면 임시 텍스트로 저장됩니다.
                </p>
                <button
                  type="button"
                  onClick={addClientToDb}
                  disabled={clientAdding}
                  className="rounded-md border border-zinc-300 px-2 py-0.5 text-[10px] hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
                >
                  {clientAdding ? "추가 중..." : "발주처 DB에 추가"}
                </button>
              </div>
            )}
            {clientMatch && client.trim() && (
              <p className="mt-1 text-[10px] text-emerald-500">
                ✓ 매칭: {clientMatch.name}
                {clientMatch.category ? ` (${clientMatch.category})` : ""}
              </p>
            )}
          </Field>
        </div>

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
        <MultiSelectChips
          label="담당자"
          value={assignees}
          onChange={setAssignees}
          options={[]}
          placeholder="이름 입력 후 Enter (콤마/엔터로 추가)"
          full
        />
        <MultiSelectChips
          label="업무내용"
          value={workTypes}
          onChange={setWorkTypes}
          options={workTypeOptions}
          placeholder={
            workTypeOptions.length > 0
              ? "선택 또는 신규 입력"
              : "옵션 불러오는 중..."
          }
          full
        />

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
              type="text"
              inputMode="numeric"
              value={amount === "" ? "" : Number(amount).toLocaleString("ko-KR")}
              onChange={(e) => {
                const digits = e.target.value.replace(/[^\d]/g, "");
                setAmount(digits);
              }}
              placeholder="₩ 0"
              className={inputCls}
            />
          </Field>
          <Field label="VAT">
            <input
              type="text"
              inputMode="numeric"
              value={vat === "" ? "" : Number(vat).toLocaleString("ko-KR")}
              onChange={(e) => {
                const digits = e.target.value.replace(/[^\d]/g, "");
                setVat(digits);
              }}
              placeholder="₩ 0"
              className={inputCls}
            />
          </Field>
        </div>

        <ContractItemsEditor
          value={contractItems}
          onChange={setContractItems}
          clientData={clientData}
          contractAmount={amount === "" ? undefined : Number(amount)}
          vat={vat === "" ? undefined : Number(vat)}
          onSyncTotalsFromItems={syncTotalsFromItems}
          onAddClientToDb={addContractClient}
        />

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

function arraysEqual(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
}

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
