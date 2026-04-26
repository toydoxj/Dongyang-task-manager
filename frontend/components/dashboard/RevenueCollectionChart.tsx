"use client";

import {
  Bar,
  CartesianGrid,
  ComposedChart,
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
  monthsBack?: number; // 기본 12개월
}

interface MonthBucket {
  month: string; // YYYY-MM
  revenue: number; // 시작일 기준 월별 용역비 합 (막대)
  collection: number; // 월별 수금 합 (라인)
  cumCollection: number; // 누적 수금 (라인)
}

function monthKey(iso: string | null): string | null {
  if (!iso) return null;
  return iso.slice(0, 7); // YYYY-MM
}

function buildBuckets(
  projects: Project[],
  incomes: CashflowEntry[],
  monthsBack: number,
): MonthBucket[] {
  // 최근 N 개월 키 생성
  const now = new Date();
  const keys: string[] = [];
  for (let i = monthsBack - 1; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    keys.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  }
  const idx = new Map<string, MonthBucket>();
  for (const k of keys) {
    idx.set(k, { month: k, revenue: 0, collection: 0, cumCollection: 0 });
  }

  for (const p of projects) {
    const k = monthKey(p.start_date);
    if (k && idx.has(k)) {
      // 수금 목표 = 용역비(VAT 제외) + 부가세
      idx.get(k)!.revenue += (p.contract_amount ?? 0) + (p.vat ?? 0);
    }
  }
  for (const e of incomes) {
    const k = monthKey(e.date);
    if (k && idx.has(k)) {
      idx.get(k)!.collection += e.amount;
    }
  }

  // 누적
  let cum = 0;
  const result: MonthBucket[] = [];
  for (const k of keys) {
    const b = idx.get(k)!;
    cum += b.collection;
    b.cumCollection = cum;
    result.push(b);
  }
  return result;
}

export default function RevenueCollectionChart({
  projects,
  incomes,
  monthsBack = 12,
}: Props) {
  const buckets = buildBuckets(projects, incomes, monthsBack);

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <header className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">월별 매출 / 수금 추이</h3>
          <p className="text-[11px] text-zinc-500">
            막대 = 신규 계약 매출 (시작일 기준), 라인 = 월 수금 누적
          </p>
        </div>
        <span className="text-[11px] text-zinc-500">최근 {monthsBack}개월</span>
      </header>

      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={buckets} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(120,120,120,0.15)" />
            <XAxis
              dataKey="month"
              fontSize={10}
              tickFormatter={(v: string) => v.slice(2)} // YY-MM
            />
            <YAxis
              yAxisId="left"
              fontSize={10}
              tickFormatter={(v: number) => `${(v / 1e8).toFixed(1)}억`}
            />
            <YAxis
              yAxisId="right"
              orientation="right"
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
            <Bar yAxisId="left" dataKey="revenue" name="매출" fill="#6366f1" radius={[3, 3, 0, 0]} />
            <Line
              yAxisId="right"
              dataKey="cumCollection"
              name="누적 수금"
              type="monotone"
              stroke="#10b981"
              strokeWidth={2}
              dot={{ r: 2 }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
