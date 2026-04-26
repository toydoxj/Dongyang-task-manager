"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { CashflowEntry } from "@/lib/domain";
import { formatWon } from "@/lib/format";

interface Props {
  expenses: CashflowEntry[];
  monthsBack?: number;
  topN?: number;
}

const STACK_COLORS = [
  "#6366f1", // indigo
  "#10b981", // emerald
  "#f59e0b", // amber
  "#ef4444", // red
  "#8b5cf6", // violet
  "#94a3b8", // slate (기타)
];

interface Row {
  month: string;
  [category: string]: string | number;
}

function monthKey(iso: string | null): string | null {
  if (!iso) return null;
  return iso.slice(0, 7);
}

function build(
  expenses: CashflowEntry[],
  monthsBack: number,
  topN: number,
): { rows: Row[]; categories: string[] } {
  const now = new Date();
  const months: string[] = [];
  for (let i = monthsBack - 1; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    months.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  }
  const monthSet = new Set(months);

  // 카테고리별 총합으로 Top N 추출
  const totals = new Map<string, number>();
  const filtered = expenses.filter((e) => {
    const k = monthKey(e.date);
    return k != null && monthSet.has(k);
  });
  for (const e of filtered) {
    const cat = e.category || "(미분류)";
    totals.set(cat, (totals.get(cat) ?? 0) + e.amount);
  }
  const sorted = [...totals.entries()].sort((a, b) => b[1] - a[1]);
  const top = sorted.slice(0, topN).map(([c]) => c);
  const useEtc = sorted.length > topN;
  const categories = useEtc ? [...top, "기타"] : top;

  // 월별 buckets 초기화
  const rows: Row[] = months.map((m) => {
    const r: Row = { month: m };
    for (const c of categories) r[c] = 0;
    return r;
  });
  const idx = new Map(rows.map((r) => [r.month, r]));

  for (const e of filtered) {
    const k = monthKey(e.date)!;
    const r = idx.get(k);
    if (!r) continue;
    const cat = e.category || "(미분류)";
    const target = top.includes(cat) ? cat : useEtc ? "기타" : null;
    if (target) r[target] = (r[target] as number) + e.amount;
  }

  return { rows, categories };
}

export default function ExpenseTrend({
  expenses,
  monthsBack = 12,
  topN = 5,
}: Props) {
  const { rows, categories } = build(expenses, monthsBack, topN);
  const total = rows.reduce(
    (s, r) => s + categories.reduce((s2, c) => s2 + (r[c] as number), 0),
    0,
  );

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <header className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">지출 구분 월간 추이</h3>
          <p className="text-[10px] text-zinc-500">
            Top {topN} + 기타 / 최근 {monthsBack}개월 stacked area
          </p>
        </div>
        <span className="text-[11px] text-zinc-500">
          합계 {formatWon(total, true)}
        </span>
      </header>

      {total === 0 ? (
        <div className="flex h-56 items-center justify-center text-xs text-zinc-500">
          최근 {monthsBack}개월 지출 내역이 없습니다.
        </div>
      ) : (
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={rows} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(120,120,120,0.15)" />
              <XAxis
                dataKey="month"
                fontSize={10}
                tickFormatter={(v: string) => v.slice(2)}
              />
              <YAxis
                fontSize={10}
                tickFormatter={(v: number) =>
                  v >= 1e8 ? `${(v / 1e8).toFixed(1)}억` : `${(v / 1e4).toFixed(0)}만`
                }
              />
              <Tooltip
                formatter={(value, name) => [
                  formatWon(typeof value === "number" ? value : Number(value)),
                  String(name),
                ]}
                contentStyle={{
                  background: "rgba(20,20,20,0.92)",
                  border: "1px solid rgba(255,255,255,0.1)",
                  borderRadius: 6,
                  fontSize: 11,
                }}
                labelStyle={{ color: "#aaa" }}
              />
              <Legend wrapperStyle={{ fontSize: 10 }} />
              {categories.map((c, i) => (
                <Area
                  key={c}
                  type="monotone"
                  dataKey={c}
                  stackId="1"
                  stroke={STACK_COLORS[i % STACK_COLORS.length]}
                  fill={STACK_COLORS[i % STACK_COLORS.length]}
                  fillOpacity={0.6}
                />
              ))}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
