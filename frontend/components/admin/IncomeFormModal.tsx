"use client";

import { useMemo, useState } from "react";
import { useSWRConfig } from "swr";

import ProjectEditModal from "@/components/project/ProjectEditModal";
import Modal from "@/components/ui/Modal";
import {
  createIncome,
  deleteIncome,
  updateIncome,
} from "@/lib/api";
import type { CashflowEntry, Project } from "@/lib/domain";
import { keys, useCashflow, useContractItems } from "@/lib/hooks";

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

/** 한국식 단위 축약 (억/천만/백만/만). 0이면 '0'. */
function fmtKor(v: number): string {
  if (!v) return "0";
  const abs = Math.abs(v);
  if (abs >= 1e8) return `${(v / 1e8).toFixed(1)}억`;
  if (abs >= 1e7) return `${(v / 1e7).toFixed(1)}천만`;
  if (abs >= 1e6) return `${Math.round(v / 1e6)}백만`;
  if (abs >= 1e4) return `${Math.round(v / 1e4)}만`;
  return v.toLocaleString("ko-KR");
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
  const [contractItemId, setContractItemId] = useState<string | null>(
    entry?.contract_item_id ?? null,
  );
  const [note, setNote] = useState(entry?.note ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [projectEditOpen, setProjectEditOpen] = useState(false);

  const { mutate: globalMutate } = useSWRConfig();
  // 선택한 프로젝트의 contract items 후보. 프로젝트 미선택 시 fetch 안 함.
  const { data: contractItemsData, mutate: mutateItems } = useContractItems(
    selectedProjectId,
  );
  // dropdown에 분담 항목별 기성금(누적 수금) 표시 — 전체 income 호출 후 client side 합산
  const { data: incomeData } = useCashflow(
    { flow: "income" },
    !!selectedProjectId,
  );

  // 분담 항목별 누적 수금합 (편집 중인 row는 제외해야 정확한 '이 row 외 기성금')
  const paidByItem = useMemo(() => {
    const map = new Map<string, number>();
    for (const e of incomeData?.items ?? []) {
      if (!e.contract_item_id) continue;
      if (entry && e.id === entry.id) continue; // 자기 자신 제외
      map.set(
        e.contract_item_id,
        (map.get(e.contract_item_id) ?? 0) + e.amount,
      );
    }
    return map;
  }, [incomeData, entry]);

  const projectMatches = projectQuery.trim()
    ? projects
        .filter((p) =>
          p.name.toLowerCase().includes(projectQuery.toLowerCase()) ||
          p.code.toLowerCase().includes(projectQuery.toLowerCase()),
        )
        .slice(0, 8)
    : [];

  // contract items가 1개면 사용자가 명시 변경 안 했을 때 자동 매칭, 0개면 legacy
  const items = contractItemsData?.items ?? [];
  const effectiveContractItemId =
    contractItemId !== null
      ? contractItemId
      : items.length === 1
        ? items[0].id
        : null;

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
      const projectIds = selectedProjectId ? [selectedProjectId] : [];
      const body = {
        date,
        amount: Number(amount),
        round_no: roundNo ? Number(roundNo) : null,
        project_ids: projectIds,
        contract_item_id: effectiveContractItemId,
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
                      // 새 프로젝트 선택 시 contract item 매칭 reset
                      setContractItemId(null);
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
            <div className="mt-1 flex items-center gap-2">
              <p className="text-[10px] text-emerald-500">
                ✓ 선택됨 ({selectedProjectId.slice(0, 8)}...)
              </p>
              <button
                type="button"
                onClick={() => setProjectEditOpen(true)}
                className="rounded-md border border-zinc-300 px-1.5 py-0.5 text-[10px] hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
                title="프로젝트 정보 / 계약 분담 편집"
              >
                ⚙ 프로젝트 편집
              </button>
            </div>
          )}
          {selectedProjectId &&
            (() => {
              const proj = projects.find((p) => p.id === selectedProjectId);
              const clients =
                proj?.client_names && proj.client_names.length > 0
                  ? proj.client_names.join(", ")
                  : proj?.client_text || "(미지정)";
              return (
                <p className="mt-1 text-[11px] text-zinc-600 dark:text-zinc-400">
                  발주처: <span className="font-medium">{clients}</span>
                </p>
              );
            })()}
        </Field>

        {selectedProjectId && items.length > 0 && (
          <Field
            label={`분담 항목 ${items.length === 1 ? "(자동)" : `(${items.length}개)`}`}
          >
            <select
              value={effectiveContractItemId ?? ""}
              onChange={(e) => setContractItemId(e.target.value || null)}
              className={inputCls}
              disabled={items.length === 1}
            >
              {items.length > 1 && <option value="">선택…</option>}
              {items.map((it) => {
                const total = it.amount + it.vat;
                const paid = paidByItem.get(it.id) ?? 0;
                const ratio = total > 0 ? (paid / total) * 100 : 0;
                const head = `${it.client_name || "(미매칭)"}(${it.label})`;
                return (
                  <option key={it.id} value={it.id}>
                    {head} · 총 {fmtKor(total)} / 기성 {fmtKor(paid)} (
                    {ratio.toFixed(0)}%)
                  </option>
                );
              })}
            </select>
            {items.length === 1 && (
              <p className="mt-1 text-[10px] text-zinc-500">
                항목이 1개라 자동 선택됩니다.
              </p>
            )}
            {effectiveContractItemId &&
              (() => {
                const it = items.find((i) => i.id === effectiveContractItemId);
                if (!it) return null;
                const paid = paidByItem.get(it.id) ?? 0;
                return (
                  <div className="mt-2 grid grid-cols-3 gap-2 rounded-md border border-zinc-200 bg-zinc-50 p-2 dark:border-zinc-700 dark:bg-zinc-900">
                    <div>
                      <div className="text-[10px] text-zinc-500">
                        용역비 (VAT 제외)
                      </div>
                      <div className="text-xs font-medium tabular-nums">
                        ₩ {it.amount.toLocaleString("ko-KR")}
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] text-zinc-500">VAT</div>
                      <div className="text-xs font-medium tabular-nums">
                        ₩ {it.vat.toLocaleString("ko-KR")}
                      </div>
                    </div>
                    <div>
                      <div className="text-[10px] text-zinc-500">
                        기성금 (이전까지)
                      </div>
                      <div className="text-xs font-medium tabular-nums">
                        ₩ {paid.toLocaleString("ko-KR")}
                      </div>
                    </div>
                  </div>
                );
              })()}
          </Field>
        )}

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

      <ProjectEditModal
        project={
          projectEditOpen
            ? projects.find((p) => p.id === selectedProjectId) ?? null
            : null
        }
        onClose={() => setProjectEditOpen(false)}
        onSaved={() => {
          // 프로젝트 본체 + contract items 모두 재검증 — 분담 모드 dropdown/미수금 즉시 반영
          void mutateItems();
          void globalMutate(keys.projects());
          void globalMutate(["contract-items", "all"]);
        }}
      />
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
