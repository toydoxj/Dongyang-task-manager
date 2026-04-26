"use client";

import {
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

import type { CashflowEntry } from "@/lib/domain";
import { formatWon } from "@/lib/format";

interface Props {
  entries: CashflowEntry[];
}

const COLORS = [
  "#6366f1", // indigo
  "#10b981", // emerald
  "#f59e0b", // amber
  "#ef4444", // red
  "#8b5cf6", // violet
  "#94a3b8", // slate (기타)
];

interface Slice {
  category: string;
  value: number;
}

function buildSlices(entries: CashflowEntry[]): Slice[] {
  const buckets = new Map<string, number>();
  for (const e of entries) {
    if (e.type !== "expense") continue;
    const key = e.category || "(미분류)";
    buckets.set(key, (buckets.get(key) ?? 0) + e.amount);
  }
  const sorted = [...buckets.entries()]
    .map(([category, value]) => ({ category, value }))
    .sort((a, b) => b.value - a.value);

  if (sorted.length <= 5) return sorted;
  const top = sorted.slice(0, 5);
  const rest = sorted.slice(5).reduce((s, x) => s + x.value, 0);
  return [...top, { category: "기타", value: rest }];
}

export default function ExpenseBreakdown({ entries }: Props) {
  const slices = buildSlices(entries);
  const total = slices.reduce((s, x) => s + x.value, 0);

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <header className="mb-3">
        <h3 className="text-sm font-semibold">지출 구분 분포</h3>
        <p className="text-[10px] text-zinc-500">
          Top 5 + 기타 / 총 {formatWon(total, true)}
        </p>
      </header>

      {total === 0 ? (
        <div className="flex h-56 items-center justify-center text-xs text-zinc-500">
          지출 내역이 없습니다.
        </div>
      ) : (
        <div className="grid grid-cols-1 items-center gap-3 md:grid-cols-2">
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={slices}
                  dataKey="value"
                  nameKey="category"
                  cx="50%"
                  cy="50%"
                  innerRadius={50}
                  outerRadius={85}
                  paddingAngle={2}
                  stroke="none"
                >
                  {slices.map((s, i) => (
                    <Cell key={s.category} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
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
                />
              </PieChart>
            </ResponsiveContainer>
          </div>

          <ul className="space-y-1 text-xs">
            {slices.map((s, i) => (
              <li key={s.category} className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span
                    className="h-2.5 w-2.5 shrink-0 rounded-sm"
                    style={{ background: COLORS[i % COLORS.length] }}
                  />
                  <span className="truncate text-zinc-700 dark:text-zinc-300">
                    {s.category}
                  </span>
                </div>
                <div className="shrink-0 text-right">
                  <span className="font-medium">{formatWon(s.value, true)}</span>
                  <span className="ml-1.5 text-[10px] text-zinc-500">
                    {((s.value / total) * 100).toFixed(0)}%
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
