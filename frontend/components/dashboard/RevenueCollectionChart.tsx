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

function linearRegression(values: number[]): {
  slope: number;
  intercept: number;
} {
  const n = values.length;
  if (n === 0) return { slope: 0, intercept: 0 };
  let sumX = 0;
  let sumY = 0;
  let sumXY = 0;
  let sumX2 = 0;
  for (let i = 0; i < n; i++) {
    sumX += i;
    sumY += values[i];
    sumXY += i * values[i];
    sumX2 += i * i;
  }
  const denom = n * sumX2 - sumX * sumX;
  if (denom === 0) return { slope: 0, intercept: sumY / n };
  const slope = (n * sumXY - sumX * sumY) / denom;
  const intercept = (sumY - slope * sumX) / n;
  return { slope, intercept };
}

function buildBuckets(
  projects: Project[],
  incomes: CashflowEntry[],
  expenses: CashflowEntry[],
  monthsBack: number,
): MonthBucket[] {
  const now = new Date();
  const keys: string[] = [];
  for (let i = monthsBack - 1; i >= 0; i--) {
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

  // 선형회귀 — 시리즈별로 12개월 전체를 회귀해 trend 값을 계산
  const ordered = keys.map((k) => idx.get(k)!);
  const revenues = ordered.map((b) => b.revenue);
  const collections = ordered.map((b) => b.collection);
  const expensesArr = ordered.map((b) => b.expense);
  const r = linearRegression(revenues);
  const c = linearRegression(collections);
  const x = linearRegression(expensesArr);
  ordered.forEach((b, i) => {
    // 회귀선은 음수도 그대로 — 하락 추세를 사실대로 표현
    b.revenueTrend = r.intercept + r.slope * i;
    b.collectionTrend = c.intercept + c.slope * i;
    b.expenseTrend = x.intercept + x.slope * i;
  });
  return ordered;
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
            막대 = 월별 실적, 점선 = 12개월 선형회귀 추세선
          </p>
        </div>
        <span className="text-[11px] text-zinc-500">최근 {monthsBack}개월</span>
      </header>

      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={buckets}
            margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
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
