"use client";

import {
  Bar,
  CartesianGrid,
  ComposedChart,
  LabelList,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { CashflowEntry, Project } from "@/lib/domain";
import { formatWon } from "@/lib/format";

interface Props {
  projects: Project[];
  incomes: CashflowEntry[];
  expenses: CashflowEntry[];
  monthsBack?: number; // 기본 12개월
}

interface MonthBucket {
  month: string;        // YYYY-MM
  revenue: number;      // 수주액 (시작일 기준 월별 용역비+VAT)
  collection: number;   // 수금액 (월별)
  expense: number;      // 지출액 (월별)
  revenueTrend: number;    // 수주액 선형회귀 추세
  collectionTrend: number; // 수금액 선형회귀 추세
  expenseTrend: number;    // 지출액 선형회귀 추세
}

function monthKey(iso: string | null): string | null {
  if (!iso) return null;
  return iso.slice(0, 7);
}

/** 막대 위 라벨용 — 큰 단위로 자동 축약. 0/너무 작은 값은 빈 문자열. */
function shortWon(v: number): string {
  if (!v) return "";
  const abs = Math.abs(v);
  if (abs >= 1e8) return `${(v / 1e8).toFixed(1)}억`;
  if (abs >= 1e7) return `${(v / 1e7).toFixed(1)}천만`;
  if (abs >= 1e6) return `${Math.round(v / 1e6)}백만`;
  if (abs >= 1e4) return `${Math.round(v / 1e4)}만`;
  return "";
}

function buildBuckets(
  projects: Project[],
  incomes: CashflowEntry[],
  expenses: CashflowEntry[],
  monthsBack: number,
): MonthBucket[] {
  // PR-FJ (사용자 요청, 2026-05-17): 추세선을 선형회귀 → rolling 12개월 평균으로 변경.
  // 정확한 trailing average를 위해 데이터 윈도우를 2배(24개월)로 만들고 trend 계산 후
  // 차트에는 마지막 monthsBack(=12)개월만 표시. 가장 옛 월도 직전 12개월 평균 사용 가능.
  const now = new Date();
  const windowSize = monthsBack * 2;
  const keys: string[] = [];
  for (let i = windowSize - 1; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    keys.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  }
  const idx = new Map<string, MonthBucket>();
  for (const k of keys) {
    idx.set(k, {
      month: k,
      revenue: 0,
      collection: 0,
      expense: 0,
      revenueTrend: 0,
      collectionTrend: 0,
      expenseTrend: 0,
    });
  }

  for (const p of projects) {
    const k = monthKey(p.start_date);
    const b = k ? idx.get(k) : undefined;
    if (b) b.revenue += (p.contract_amount ?? 0) + (p.vat ?? 0);
  }
  for (const e of incomes) {
    const k = monthKey(e.date);
    const b = k ? idx.get(k) : undefined;
    if (b) b.collection += e.amount;
  }
  for (const e of expenses) {
    const k = monthKey(e.date);
    const b = k ? idx.get(k) : undefined;
    if (b) b.expense += e.amount;
  }

  // Rolling 12개월 평균 — 각 월 시점의 그 월 포함 직전 monthsBack개월 평균.
  // 윈도우의 첫 monthsBack-1 월은 차트에 표시 안 됨 (trend 계산 source로만 사용).
  const ordered = keys.map((k) => idx.get(k)!);
  ordered.forEach((b, i) => {
    const start = Math.max(0, i - monthsBack + 1);
    const slice = ordered.slice(start, i + 1);
    const n = slice.length;
    b.revenueTrend = slice.reduce((s, x) => s + x.revenue, 0) / n;
    b.collectionTrend = slice.reduce((s, x) => s + x.collection, 0) / n;
    b.expenseTrend = slice.reduce((s, x) => s + x.expense, 0) / n;
  });
  // 차트 표시는 마지막 monthsBack 월만 (앞 monthsBack 월은 trend 계산 보조).
  return ordered.slice(-monthsBack);
}

export default function RevenueCollectionChart({
  projects,
  incomes,
  expenses,
  monthsBack = 12,
}: Props) {
  const buckets = buildBuckets(projects, incomes, expenses, monthsBack);

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <header className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">월별 수주 / 수금 / 지출 추이</h3>
          <p className="text-[11px] text-zinc-500">
            막대 = 월별 실적, 점선 = 직전 12개월 rolling 평균
          </p>
        </div>
        <span className="text-[11px] text-zinc-500">최근 {monthsBack}개월</span>
      </header>

      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={buckets}
            margin={{ top: 10, right: 24, left: 0, bottom: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(120,120,120,0.15)" />
            <XAxis
              dataKey="month"
              fontSize={10}
              tickFormatter={(v: string) => v.slice(2)}
            />
            <YAxis
              fontSize={10}
              tickFormatter={(v: number) => `${(v / 1e8).toFixed(1)}억`}
            />
            <Tooltip
              formatter={(value, name) => [
                formatWon(typeof value === "number" ? value : Number(value)),
                String(name),
              ]}
              labelFormatter={(label) => String(label)}
              contentStyle={{
                background: "rgba(20,20,20,0.92)",
                border: "1px solid rgba(255,255,255,0.1)",
                borderRadius: 6,
                fontSize: 11,
              }}
              labelStyle={{ color: "#aaa" }}
            />
            <Bar
              dataKey="revenue"
              name="수주액"
              fill="#6366f1"
              radius={[3, 3, 0, 0]}
            >
              <LabelList
                dataKey="revenue"
                position="top"
                fontSize={9}
                fill="#6366f1"
                formatter={(v: unknown) => shortWon(Number(v) || 0)}
              />
            </Bar>
            <Bar
              dataKey="collection"
              name="수금액"
              fill="#10b981"
              radius={[3, 3, 0, 0]}
            >
              <LabelList
                dataKey="collection"
                position="top"
                fontSize={9}
                fill="#10b981"
                formatter={(v: unknown) => shortWon(Number(v) || 0)}
              />
            </Bar>
            <Bar
              dataKey="expense"
              name="지출액"
              fill="#f97316"
              radius={[3, 3, 0, 0]}
            >
              <LabelList
                dataKey="expense"
                position="top"
                fontSize={9}
                fill="#f97316"
                formatter={(v: unknown) => shortWon(Number(v) || 0)}
              />
            </Bar>
            <Line
              dataKey="revenueTrend"
              name="수주 추세"
              type="linear"
              stroke="#6366f1"
              strokeWidth={1.5}
              strokeDasharray="4 3"
              dot={false}
              activeDot={false}
            />
            <Line
              dataKey="collectionTrend"
              name="수금 추세"
              type="linear"
              stroke="#10b981"
              strokeWidth={1.5}
              strokeDasharray="4 3"
              dot={false}
              activeDot={false}
            />
            <Line
              dataKey="expenseTrend"
              name="지출 추세"
              type="linear"
              stroke="#f97316"
              strokeWidth={1.5}
              strokeDasharray="4 3"
              dot={false}
              activeDot={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
