"use client";

import type { QuoteResult } from "@/lib/domain";

const KRW = (n: number): string => n.toLocaleString("ko-KR") + "원";

interface Props {
  result: QuoteResult | null;
  loading?: boolean;
}

export default function QuoteResultPanel({ result, loading }: Props) {
  if (loading && !result) {
    return (
      <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-4 text-xs text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900">
        산출 중…
      </div>
    );
  }
  if (!result) {
    return (
      <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-4 text-xs text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900">
        연면적과 요율을 입력하면 산출 결과가 표시됩니다.
      </div>
    );
  }

  return (
    <div className="space-y-2 rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-3 text-xs">
      <Row
        label="작업 기준인원 (인.일)"
        value={`${result.manhours_baseline_rounded} × 요율들 = ${result.manhours_total}`}
        mono
      />
      <hr className="border-emerald-500/20" />
      <Row label="① 직접인건비" value={KRW(result.direct_labor)} mono />
      <Row
        label="② 직접경비 (인쇄+조사+교통)"
        value={KRW(result.direct_expense)}
        mono
      />
      <Row label="⑥ 제경비 (①×110%)" value={KRW(result.overhead)} mono />
      <Row
        label="⑦ 기술료 ((①+⑥)×20%)"
        value={KRW(result.tech_fee)}
        mono
      />
      <Row label="⑧ 합계 (①+⑥+⑦)" value={KRW(result.subtotal)} mono />
      <Row
        label="⑨ 당사조정 (⑧×조정%+②)"
        value={KRW(result.adjusted)}
        mono
      />
      <Row label="⑩ 절삭 (백만 미만)" value={`-${KRW(result.truncated)}`} mono />
      <hr className="border-emerald-500/30" />
      <Row
        label="⑪ 용역대가"
        value={KRW(result.final)}
        mono
        highlight
      />
      {result.per_pyeong > 0 && (
        <Row
          label={`평당 단가 (${result.per_pyeong_area.toFixed(1)}평)`}
          value={`${result.per_pyeong.toLocaleString("ko-KR", { maximumFractionDigits: 0 })}원/평`}
          mono
        />
      )}
    </div>
  );
}

function Row({
  label,
  value,
  mono,
  highlight,
}: {
  label: string;
  value: string;
  mono?: boolean;
  highlight?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span
        className={
          highlight
            ? "text-sm font-semibold text-emerald-700 dark:text-emerald-400"
            : "text-zinc-600 dark:text-zinc-400"
        }
      >
        {label}
      </span>
      <span
        className={
          (mono ? "font-mono " : "") +
          (highlight
            ? "text-sm font-bold text-emerald-700 dark:text-emerald-400"
            : "text-zinc-800 dark:text-zinc-200")
        }
      >
        {value}
      </span>
    </div>
  );
}
