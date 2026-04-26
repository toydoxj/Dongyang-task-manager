"use client";

import {
  Area,
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
  project: Project;
  entries: CashflowEntry[];
}

interface Bucket {
  month: string; // YYYY-MM
  income: number;
  expense: number;
  cumIncome: number;
  cumExpense: number;
}

function monthKey(iso: string | null): string | null {
  if (!iso) return null;
  return iso.slice(0, 7);
}

function buildBuckets(entries: CashflowEntry[]): Bucket[] {
  const idx = new Map<string, Bucket>();
  for (const e of entries) {
    const k = monthKey(e.date);
    if (!k) continue;
    const b = idx.get(k) ?? {
      month: k,
      income: 0,
      expense: 0,
      cumIncome: 0,
      cumExpense: 0,
    };
    if (e.type === "income") b.income += e.amount;
    else b.expense += e.amount;
    idx.set(k, b);
  }
  const sorted = [...idx.values()].sort((a, b) => a.month.localeCompare(b.month));
  let cI = 0,
    cE = 0;
  for (const b of sorted) {
    cI += b.income;
    cE += b.expense;
    b.cumIncome = cI;
    b.cumExpense = cE;
  }
  return sorted;
}

export default function ProjectCashflowChart({ project, entries }: Props) {
  const buckets = buildBuckets(entries);
  // 수금 목표 = 용역비(VAT 제외) + 부가세. VAT 미입력 시 contract_amount × 10% 추정.
  const base = project.contract_amount ?? 0;
  const vat = project.vat ?? base * 0.1;
  const target = base + vat;

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <header className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">현금흐름 (실측)</h3>
          <p className="text-[10px] text-zinc-500">
            영역 = 누적 수금/지출, 점선 = 용역비 + 부가세 목표선
          </p>
        </div>
        <div className="flex gap-3 text-[10px]">
          <span>
            <span className="mr-1 inline-block h-2 w-2 rounded-sm bg-emerald-500/60" />
            수금 누적
          </span>
          <span>
            <span className="mr-1 inline-block h-2 w-2 rounded-sm bg-red-500/60" />
            지출 누적
          </span>
        </div>
      </header>

      {buckets.length === 0 ? (
        <div className="flex h-56 items-center justify-center text-xs text-zinc-500">
          거래 내역이 없습니다.
        </div>
      ) : (
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={buckets} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(120,120,120,0.15)" />
              <XAxis dataKey="month" fontSize={10} tickFormatter={(v: string) => v.slice(2)} />
              <YAxis
                fontSize={10}
                tickFormatter={(v: number) => `${(v / 1e8).toFixed(1)}억`}
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
              <Area
                type="monotone"
                dataKey="cumIncome"
                name="수금 누적"
                stroke="#10b981"
                fill="#10b981"
                fillOpacity={0.25}
              />
              <Area
                type="monotone"
                dataKey="cumExpense"
                name="지출 누적"
                stroke="#ef4444"
                fill="#ef4444"
                fillOpacity={0.2}
              />
              {target > 0 && (
                <Line
                  type="monotone"
                  dataKey={() => target}
                  name="용역비+부가세"
                  stroke="#a3a3a3"
                  strokeDasharray="4 4"
                  dot={false}
                />
              )}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
