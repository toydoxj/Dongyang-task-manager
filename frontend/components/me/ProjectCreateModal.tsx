"use client";

import { useState } from "react";
import { useSWRConfig } from "swr";

import { useAuth } from "@/components/AuthGuard";
import Modal from "@/components/ui/Modal";
import MultiSelectChips from "@/components/ui/MultiSelectChips";
import { createClient, createProject } from "@/lib/api";
import type { ClientListResponse } from "@/lib/domain";
import { keys, useClients, useProjectOptions } from "@/lib/hooks";

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
  /** 다른 직원 명의 생성 (admin/team_lead). 지정 시 그 사람이 자동 담당자. */
  forUser?: string;
}

export default function ProjectCreateModal({
  open,
  onClose,
  onCreated,
  forUser,
}: Props) {
  const { user } = useAuth();
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [client, setClient] = useState("");
  const [assignees, setAssignees] = useState<string[]>(
    user?.name ? [user.name] : [],
  );
  const [workTypes, setWorkTypes] = useState<string[]>([]);
  const [startDate, setStartDate] = useState("");
  const [contractStart, setContractStart] = useState("");
  const [contractEnd, setContractEnd] = useState("");
  const [amount, setAmount] = useState("");
  const [vat, setVat] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [clientAdding, setClientAdding] = useState(false);

  const { data: optionsData } = useProjectOptions(open);
  const workTypeOptions = optionsData?.work_types ?? [];
  const { mutate } = useSWRConfig();
  // 협력업체 목록 (모달 열릴 때만 fetch)
  const { data: clientData } = useClients(open);
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
      // race 회피: SWR 캐시에 즉시 주입 후 setClient
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

  const reset = (): void => {
    setName("");
    setCode("");
    setClient("");
    setAssignees(user?.name ? [user.name] : []);
    setWorkTypes([]);
    setStartDate("");
    setContractStart("");
    setContractEnd("");
    setAmount("");
    setVat("");
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
      await createProject(
        {
          name: name.trim(),
          code: code.trim() || undefined,
          // 협력업체 매칭되면 relation 으로, 아니면 text fallback
          client_relation_ids: clientMatch ? [clientMatch.id] : undefined,
          client_text: clientMatch ? undefined : trimmedClient || undefined,
          // 담당팀은 폼에서 제거 — 노션 자동 집계에 위임
          assignees,
          work_types: workTypes,
          start_date: startDate || undefined,
          contract_start: contractStart || undefined,
          contract_end: contractEnd || undefined,
          contract_amount: amount ? Number(amount) : undefined,
          vat: vat ? Number(vat) : undefined,
        },
        { forUser },
      );
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
          노션 메인 DB에 새 프로젝트 페이지를 생성합니다.{" "}
          {forUser
            ? `${forUser} 님이 자동으로 담당자에 추가됩니다.`
            : "본인이 자동으로 담당자에 추가됩니다."}
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
