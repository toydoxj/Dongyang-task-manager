"use client";

/**
 * SalesEditModal 견적 list view 내부 inline form — 외부 견적 추가/수정.
 * 산출 X (산식 없음). service + amount + vat_included만 입력.
 *
 * PR-AF — SalesEditModal.tsx에서 추출 (외과적 변경 / 동작 동일).
 */

import { inputCls } from "./_shared";

export interface ExternalQuoteDraft {
  service: string;
  amount: number;
  vat_included: boolean;
}

interface Props {
  draft: ExternalQuoteDraft;
  isEdit: boolean;
  saving: boolean;
  onChange: (next: ExternalQuoteDraft) => void;
  /** 저장 액션 — 부모가 await/close/reset 처리. */
  onSubmit: () => void;
  /** 취소 — 부모가 close + reset 처리. */
  onCancel: () => void;
}

export default function ExternalQuoteForm({
  draft,
  isEdit,
  saving,
  onChange,
  onSubmit,
  onCancel,
}: Props) {
  return (
    <div className="space-y-2 rounded-md border border-amber-300 bg-amber-50/40 p-3 dark:border-amber-600/40 dark:bg-amber-900/10">
      <div className="text-xs font-medium text-amber-700 dark:text-amber-400">
        외부 견적 {isEdit ? "수정" : "추가"}
      </div>
      <input
        type="text"
        placeholder="업무내용 (예: 구조진단 외주 (B사))"
        value={draft.service}
        onChange={(e) => onChange({ ...draft, service: e.target.value })}
        className={inputCls}
      />
      <input
        type="number"
        min={0}
        placeholder="금액 (원)"
        value={draft.amount || ""}
        onChange={(e) =>
          onChange({
            ...draft,
            amount: e.target.value ? Number(e.target.value) : 0,
          })
        }
        className={inputCls}
      />
      <label className="flex items-center gap-2 text-[11px] text-amber-700 dark:text-amber-400">
        <input
          type="checkbox"
          checked={draft.vat_included}
          onChange={(e) =>
            onChange({ ...draft, vat_included: e.target.checked })
          }
        />
        VAT 포함 (체크 해제 시 VAT 별도)
      </label>
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="rounded border border-zinc-300 px-2 py-1 text-[11px] hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
        >
          취소
        </button>
        <button
          type="button"
          disabled={saving || !draft.service.trim()}
          onClick={onSubmit}
          className="rounded border border-amber-600/40 bg-amber-500/20 px-2 py-1 text-[11px] font-medium text-amber-700 hover:bg-amber-500/30 disabled:opacity-50 dark:text-amber-400"
        >
          {isEdit ? "수정" : "추가"}
        </button>
      </div>
    </div>
  );
}
