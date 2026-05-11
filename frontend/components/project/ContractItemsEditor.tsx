"use client";

/**
 * 「계약 분담」 편집 섹션 — ProjectCreate/EditModal 공통.
 *
 * 도메인:
 * - 한 프로젝트에 N개 (발주처, 라벨, 금액, VAT) 항목.
 * - 공동수급은 같은 라벨("본 계약") + 다른 발주처 row 여러 개.
 * - 추가 용역은 다른 라벨("변경설계 1차") + 발주처는 같거나 다름.
 * - 항목이 비어 있으면 부모 모달이 단일 발주처 입력 fallback 모드로 동작.
 *
 * 동작 모델:
 * - 부모는 `value: DraftItem[]`로 분담 list를 통째 보유. 본 컴포넌트는 그것의
 *   추가/수정/삭제만 한다. 실제 API 호출(create/update/delete)은 모달 저장 시
 *   부모가 diff를 계산해 일괄 처리(2차 배포 plan 그대로).
 * - 신규 행은 id="" (서버에 아직 없음). 기존 행은 노션 page_id.
 *
 * 합계 검증:
 * - sum(amount) vs contract_amount, sum(vat) vs vat 비교해 amber 경고.
 * - 자동 동기화는 부모 모달의 "분담 합계로 contract_amount 채우기" 액션에서.
 */

import { useMemo } from "react";

import type { ClientListResponse, ContractItem } from "@/lib/domain";

export interface DraftContractItem {
  id: string; // "" = 신규
  client_id: string;
  client_name: string;
  label: string;
  amount: number;
  vat: number;
  sort_order: number;
  /** 편집 추적용 — 'persistent' | 'created' | 'modified' (부모 diff 계산용). */
  _origin?: "persisted" | "created" | "modified";
}

export function toDraft(item: ContractItem): DraftContractItem {
  return {
    id: item.id,
    client_id: item.client_id,
    client_name: item.client_name ?? "",
    label: item.label,
    amount: item.amount,
    vat: item.vat,
    sort_order: item.sort_order,
    _origin: "persisted",
  };
}

interface Props {
  value: DraftContractItem[];
  onChange: (next: DraftContractItem[]) => void;
  clientData: ClientListResponse | undefined;
  /** 부모의 contract_amount/vat — 합계 검증 표시용. 비어있으면 검증 skip. */
  contractAmount?: number;
  vat?: number;
  /** "분담 합계로 contract_amount 채우기" 콜백 — 부모가 처리. */
  onSyncTotalsFromItems?: () => void;
  /**
   * 미매칭 발주처 이름을 발주처 DB에 신규 등록 후 새 page_id를 반환.
   * 부모가 createClient + SWR 캐시 invalidate를 처리한다.
   */
  onAddClientToDb?: (name: string) => Promise<string>;
  /** false면 read-only — input/버튼 비활성. 기본 true. */
  canEdit?: boolean;
}

export default function ContractItemsEditor({
  value,
  onChange,
  clientData,
  contractAmount,
  vat,
  onSyncTotalsFromItems,
  onAddClientToDb,
  canEdit = true,
}: Props) {
  const totals = useMemo(() => {
    let amount = 0;
    let v = 0;
    for (const it of value) {
      amount += it.amount || 0;
      v += it.vat || 0;
    }
    return { amount, vat: v };
  }, [value]);

  const amountMatch =
    contractAmount == null
      ? true
      : Math.abs(totals.amount - contractAmount) < 1;
  const vatMatch = vat == null ? true : Math.abs(totals.vat - vat) < 1;
  const hasMismatch =
    value.length > 0 && (!amountMatch || !vatMatch);

  const norm = (s: string): string => s.trim().toLowerCase();

  const update = (idx: number, patch: Partial<DraftContractItem>): void => {
    const next = value.slice();
    const cur = next[idx];
    next[idx] = {
      ...cur,
      ...patch,
      _origin: cur._origin === "persisted" ? "modified" : cur._origin,
    };
    onChange(next);
  };

  const add = (): void => {
    onChange([
      ...value,
      {
        id: "",
        client_id: "",
        client_name: "",
        label: "본 계약",
        amount: 0,
        vat: 0,
        sort_order: value.length,
        _origin: "created",
      },
    ]);
  };

  const remove = (idx: number): void => {
    const next = value.slice();
    next.splice(idx, 1);
    onChange(next);
  };

  return (
    <div className="rounded-md border border-zinc-200 bg-zinc-50/50 p-3 dark:border-zinc-700 dark:bg-zinc-900/40">
      <div className="mb-2 flex items-center justify-between">
        <div>
          <h3 className="text-xs font-semibold">
            계약 분담{" "}
            <span className="ml-1 text-[10px] font-normal text-zinc-500">
              (공동수급·추가용역)
            </span>
          </h3>
          <p className="text-[10px] text-zinc-500">
            비어 있으면 단일 발주처 모드로 동작. 항목이 1개 이상이면 발주처별
            미수금이 항목 단위로 계산됩니다.
          </p>
        </div>
        {canEdit && (
          <button
            type="button"
            onClick={add}
            className="rounded-md border border-zinc-300 px-2 py-0.5 text-[11px] hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
          >
            + 항목 추가
          </button>
        )}
      </div>

      {value.length === 0 ? (
        <p className="py-3 text-center text-[10px] text-zinc-400">
          항목 없음 (단일 발주처 모드)
        </p>
      ) : (
        <ul className="space-y-1.5">
          {value.map((it, idx) => (
            <li
              key={it.id || `new-${idx}`}
              className="grid grid-cols-12 items-center gap-1.5 rounded-md border border-zinc-200 bg-white p-1.5 text-xs dark:border-zinc-700 dark:bg-zinc-950"
            >
              <input
                type="text"
                value={it.label}
                onChange={(e) => update(idx, { label: e.target.value })}
                readOnly={!canEdit}
                placeholder="라벨 (본 계약 / 변경설계 1차 …)"
                className={`col-span-3 ${cellCls}`}
              />
              <input
                type="text"
                list="dy-contract-clients"
                value={it.client_name}
                onChange={(e) => {
                  const name = e.target.value;
                  const matched = clientData?.items.find(
                    (c) => norm(c.name) === norm(name),
                  );
                  update(idx, {
                    client_name: name,
                    client_id: matched?.id ?? "",
                  });
                }}
                readOnly={!canEdit}
                placeholder="발주처"
                className={`col-span-3 ${cellCls}`}
              />
              <input
                type="text"
                inputMode="numeric"
                value={
                  it.amount === 0 ? "" : Number(it.amount).toLocaleString("ko-KR")
                }
                onChange={(e) => {
                  const digits = e.target.value.replace(/[^\d]/g, "");
                  update(idx, { amount: digits ? Number(digits) : 0 });
                }}
                readOnly={!canEdit}
                placeholder="금액"
                className={`col-span-2 text-right ${cellCls}`}
              />
              <input
                type="text"
                inputMode="numeric"
                value={
                  it.vat === 0 ? "" : Number(it.vat).toLocaleString("ko-KR")
                }
                onChange={(e) => {
                  const digits = e.target.value.replace(/[^\d]/g, "");
                  update(idx, { vat: digits ? Number(digits) : 0 });
                }}
                readOnly={!canEdit}
                placeholder="VAT"
                className={`col-span-2 text-right ${cellCls}`}
              />
              <div className="col-span-2 flex items-center gap-1 justify-end">
                {canEdit && it.client_name.trim() && !it.client_id && (
                  onAddClientToDb ? (
                    <button
                      type="button"
                      onClick={async () => {
                        try {
                          const newId = await onAddClientToDb(
                            it.client_name.trim(),
                          );
                          update(idx, { client_id: newId });
                        } catch {
                          /* 부모가 에러 표시 처리 */
                        }
                      }}
                      className="rounded border border-amber-500/50 px-1.5 py-0.5 text-[9px] text-amber-500 hover:bg-amber-500/10"
                      title="발주처 DB에 신규 등록"
                    >
                      + DB추가
                    </button>
                  ) : (
                    <span
                      className="text-[9px] text-amber-500"
                      title="발주처 DB 미매칭 — 발주처 관리에서 먼저 등록하세요"
                    >
                      ⚠ 미매칭
                    </span>
                  )
                )}
                {canEdit && (
                  <button
                    type="button"
                    onClick={() => remove(idx)}
                    className="rounded p-1 text-red-500 hover:bg-red-500/10"
                    title="삭제"
                  >
                    ✕
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {/* 공통 datalist (발주처 자동완성). 컬렉션 ID는 dy-contract-clients */}
      <datalist id="dy-contract-clients">
        {clientData?.items.map((c) => (
          <option key={c.id} value={c.name}>
            {c.category}
          </option>
        ))}
      </datalist>

      {value.length > 0 && (
        <div className="mt-2 flex items-center justify-between text-[10px]">
          <span className="text-zinc-500">
            합계: 금액 {totals.amount.toLocaleString("ko-KR")} / VAT{" "}
            {totals.vat.toLocaleString("ko-KR")}
          </span>
          <div className="flex items-center gap-2">
            {hasMismatch && (
              <span className="text-amber-500">
                ⚠ 프로젝트 contract_amount / VAT와 불일치
              </span>
            )}
            {canEdit && onSyncTotalsFromItems && hasMismatch && (
              <button
                type="button"
                onClick={onSyncTotalsFromItems}
                className="rounded border border-amber-500/50 px-1.5 py-0.5 text-amber-500 hover:bg-amber-500/10"
              >
                합계로 자동 채우기
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

const cellCls =
  "rounded border border-zinc-200 bg-white px-1.5 py-1 outline-none focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-950";
