"use client";

import { useState } from "react";
import { useSWRConfig } from "swr";

import Modal from "@/components/ui/Modal";
import {
  createClient,
  createIncome,
  deleteIncome,
  updateIncome,
} from "@/lib/api";
import type {
  CashflowEntry,
  ClientListResponse,
  Project,
} from "@/lib/domain";
import { keys, useClients } from "@/lib/hooks";

interface Props {
  /** null이면 신규 등록, entry 있으면 편집 */
  entry: CashflowEntry | null;
  /** open 제어 (entry !== null이면 편집, isOpen으로 신규 표시) */
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
  projects: Project[];
}

export default function IncomeFormModal({
  entry,
  open,
  onClose,
  onSaved,
  projects,
}: Props) {
  if (!open) return null;
  return (
    <Form
      key={entry?.id ?? "new"}
      entry={entry}
      onClose={onClose}
      onSaved={onSaved}
      projects={projects}
    />
  );
}

function todayYMD(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function Form({
  entry,
  onClose,
  onSaved,
  projects,
}: {
  entry: CashflowEntry | null;
  onClose: () => void;
  onSaved: () => void;
  projects: Project[];
}) {
  const isEdit = !!entry;
  const [date, setDate] = useState(entry?.date?.slice(0, 10) ?? todayYMD());
  const [amount, setAmount] = useState(
    entry?.amount != null ? String(entry.amount) : "",
  );
  const [roundNo, setRoundNo] = useState(
    entry?.round_no != null ? String(entry.round_no) : "",
  );
  // 단일 선택 — 노션 relation은 multi 가능하나 UI는 단일로 단순화
  const initialProject = (() => {
    const pid = entry?.project_ids?.[0];
    if (!pid) return null;
    return projects.find((p) => p.id === pid) ?? null;
  })();
  const [projectQuery, setProjectQuery] = useState(initialProject?.name ?? "");
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(
    initialProject?.id ?? null,
  );
  const [payerQuery, setPayerQuery] = useState(entry?.payer_names?.[0] ?? "");
  const [note, setNote] = useState(entry?.note ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [clientAdding, setClientAdding] = useState(false);

  const { data: clientData } = useClients(true);
  const { mutate } = useSWRConfig();
  const norm = (s: string): string => s.trim().toLowerCase();
  const payerMatch =
    payerQuery.trim() === ""
      ? undefined
      : clientData?.items.find((c) => norm(c.name) === norm(payerQuery));
  const showAddPayer =
    !payerMatch && payerQuery.trim() !== "" && !clientAdding;

  const projectMatches = projectQuery.trim()
    ? projects
        .filter((p) =>
          p.name.toLowerCase().includes(projectQuery.toLowerCase()) ||
          p.code.toLowerCase().includes(projectQuery.toLowerCase()),
        )
        .slice(0, 8)
    : [];

  const addPayerToDb = async (): Promise<void> => {
    const trimmed = payerQuery.trim();
    if (!trimmed) return;
    setClientAdding(true);
    setError(null);
    try {
      const created = await createClient({ name: trimmed });
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
      setPayerQuery(created.name);
    } catch (err) {
      setError(err instanceof Error ? err.message : "발주처 등록 실패");
    } finally {
      setClientAdding(false);
    }
  };

  const submit = async (): Promise<void> => {
    if (!date) {
      setError("일자를 입력하세요");
      return;
    }
    if (!amount || Number(amount) <= 0) {
      setError("금액을 입력하세요");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const payerIds = payerMatch ? [payerMatch.id] : [];
      const projectIds = selectedProjectId ? [selectedProjectId] : [];
      const body = {
        date,
        amount: Number(amount),
        round_no: roundNo ? Number(roundNo) : null,
        project_ids: projectIds,
        payer_relation_ids: payerIds,
        note,
      };
      if (isEdit && entry) {
        await updateIncome(entry.id, body);
      } else {
        await createIncome(body);
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "저장 실패");
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async (): Promise<void> => {
    if (!entry) return;
    if (!confirm("이 수금 기록을 삭제하시겠습니까? (노션 페이지가 휴지통으로 이동)"))
      return;
    setBusy(true);
    setError(null);
    try {
      await deleteIncome(entry.id);
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "삭제 실패");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title={isEdit ? "수금 편집" : "수금 신규 등록"}
      size="md"
    >
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <Field label="수금일" required>
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className={inputCls}
              autoFocus
            />
          </Field>
          <Field label="회차">
            <input
              type="number"
              min={1}
              max={99}
              value={roundNo}
              onChange={(e) => setRoundNo(e.target.value)}
              className={inputCls}
              placeholder="예: 1"
            />
          </Field>
        </div>

        <Field label="프로젝트">
          <input
            type="text"
            value={projectQuery}
            onChange={(e) => {
              setProjectQuery(e.target.value);
              setSelectedProjectId(null);
            }}
            className={inputCls}
            placeholder="프로젝트명 또는 Sub CODE 검색"
          />
          {projectMatches.length > 0 && !selectedProjectId && (
            <ul className="mt-1 max-h-40 overflow-y-auto rounded-md border border-zinc-200 bg-white text-xs dark:border-zinc-700 dark:bg-zinc-900">
              {projectMatches.map((p) => (
                <li key={p.id}>
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedProjectId(p.id);
                      setProjectQuery(p.name);
                    }}
                    className="flex w-full items-center justify-between gap-2 px-2 py-1.5 text-left hover:bg-zinc-100 dark:hover:bg-zinc-800"
                  >
                    <span className="truncate">{p.name}</span>
                    <span className="shrink-0 font-mono text-[10px] text-zinc-500">
                      {p.code || "—"}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {selectedProjectId && (
            <p className="mt-1 text-[10px] text-emerald-500">
              ✓ 선택됨 ({selectedProjectId.slice(0, 8)}...)
            </p>
          )}
        </Field>

        <Field label="금액 (원)" required>
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

        <Field label="실지급 (발주처)">
          <input
            type="text"
            list="dy-payer-clients"
            value={payerQuery}
            onChange={(e) => setPayerQuery(e.target.value)}
            className={inputCls}
            placeholder={
              clientData
                ? "발주처 자동완성 (미등록 시 추가 가능)"
                : "협력업체 목록 불러오는 중..."
            }
          />
          <datalist id="dy-payer-clients">
            {clientData?.items.map((c) => (
              <option key={c.id} value={c.name}>
                {c.category}
              </option>
            ))}
          </datalist>
          {showAddPayer && (
            <div className="mt-1 flex items-center gap-2">
              <p className="text-[10px] text-zinc-500">
                미등록 발주처 — 추가하지 않으면 빈 relation으로 저장됩니다.
              </p>
              <button
                type="button"
                onClick={addPayerToDb}
                disabled={clientAdding}
                className="rounded-md border border-zinc-300 px-2 py-0.5 text-[10px] hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
              >
                {clientAdding ? "추가 중..." : "발주처 DB에 추가"}
              </button>
            </div>
          )}
          {payerMatch && payerQuery.trim() && (
            <p className="mt-1 text-[10px] text-emerald-500">
              ✓ 매칭: {payerMatch.name}
              {payerMatch.category ? ` (${payerMatch.category})` : ""}
            </p>
          )}
        </Field>

        <Field label="비고">
          <textarea
            rows={2}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            className={inputCls}
          />
        </Field>

        {error && (
          <p className="rounded-md border border-red-500/40 bg-red-500/5 p-2 text-xs text-red-400">
            {error}
          </p>
        )}

        <footer className="flex items-center justify-between pt-2">
          {isEdit ? (
            <button
              type="button"
              onClick={onDelete}
              disabled={busy}
              className="rounded-md border border-red-500/50 px-3 py-1.5 text-xs text-red-500 hover:bg-red-500/10 disabled:opacity-50"
            >
              삭제
            </button>
          ) : (
            <span />
          )}
          <div className="flex gap-2">
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
              {busy ? "저장 중..." : isEdit ? "저장" : "등록"}
            </button>
          </div>
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
