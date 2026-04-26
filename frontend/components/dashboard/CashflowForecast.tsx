"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { Project } from "@/lib/domain";
import { formatWon } from "@/lib/format";

interface Props {
  projects: Project[];
  monthsAhead?: number;
}

interface Bucket {
  month: string;
  expectedIncome: number;     // 예상 월 수금
  expectedExpense: number;    // 예상 월 지출 (외주비 분배)
  cumNet: number;             // 누적 순수금 (예상)
}

function monthsAheadKeys(n: number): string[] {
  const now = new Date();
  const out: string[] = [];
  for (let i = 0; i < n; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() + i, 1);
    out.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  }
  return out;
}

function monthsBetween(startKey: string, endKey: string): string[] {
  const [sy, sm] = startKey.split("-").map(Number);
  const [ey, em] = endKey.split("-").map(Number);
  const out: string[] = [];
  let y = sy,
    m = sm;
  while (y < ey || (y === ey && m <= em)) {
    out.push(`${y}-${String(m).padStart(2, "0")}`);
    m += 1;
    if (m > 12) {
      m = 1;
      y += 1;
    }
  }
  return out;
}

function build(projects: Project[], monthsAhead: number): Bucket[] {
  const horizon = monthsAheadKeys(monthsAhead);
  const horizonSet = new Set(horizon);
  const map = new Map<string, Bucket>();
  for (const k of horizon) {
    map.set(k, {
      month: k,
      expectedIncome: 0,
      expectedExpense: 0,
      cumNet: 0,
    });
  }

  const today = new Date();
  const todayKey = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;

  for (const p of projects) {
    if (p.completed) continue;
    if (["완료", "타절", "종결"].includes(p.stage)) continue;

    // 잔여 미수금
    const contract = p.contract_amount ?? 0;
    const collected = p.collection_total ?? 0;
    const remainingIncome = Math.max(0, contract - collected);

    // 잔여 외주비 (이미 지출된 건 제외 → 단순화: 외주비(예정) 전체를 잔여로 가정)
    const remainingExpense = Math.max(0, p.outsourcing_estimated ?? 0);

    if (remainingIncome <= 0 && remainingExpense <= 0) continue;

    // 잔여 계약기간 = max(today, contract_start) ~ contract_end
    const ce = p.contract_end;
    if (!ce) continue;
    const ceKey = ce.slice(0, 7);
    const startKey = todayKey > (p.contract_start?.slice(0, 7) ?? todayKey)
      ? todayKey
      : (p.contract_start?.slice(0, 7) ?? todayKey);
    if (ceKey < startKey) continue;

    const months = monthsBetween(startKey, ceKey).filter((k) => horizonSet.has(k));
    if (months.length === 0) continue;

    const monthlyIncome = remainingIncome / months.length;
    const monthlyExpense = remainingExpense / months.length;
    for (const k of months) {
      const b = map.get(k)!;
      b.expectedIncome += monthlyIncome;
      b.expectedExpense += monthlyExpense;
    }
  }

  let cum = 0;
  const buckets = horizon.map((k) => map.get(k)!);
  for (const b of buckets) {
    cum += b.expectedIncome - b.expectedExpense;
    b.cumNet = cum;
  }
  return buckets;
}

export default function CashflowForecast({ projects, monthsAhead = 12 }: Props) {
  const buckets = build(projects, monthsAhead);
  const hasData = buckets.some((b) => b.expectedIncome > 0 || b.expectedExpense > 0);

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <header className="mb-3">
        <h3 className="text-sm font-semibold">현금흐름 예측</h3>
        <p className="text-[10px] text-zinc-500">
          진행 중 프로젝트 잔여 미수금/외주비를 잔여 계약기간에 균등 분배 (향후 {monthsAhead}개월)
        </p>
      </header>

      {!hasData ? (
        <div className="flex h-56 items-center justify-center text-xs text-zinc-500">
          예측 가능한 진행 프로젝트가 없습니다 (계약기간 또는 잔액 부족).
        </div>
      ) : (
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={buckets} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
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
                contentStyle={{
                  background: "rgba(20,20,20,0.92)",
                  border: "1px solid rgba(255,255,255,0.1)",
                  borderRadius: 6,
                  fontSize: 11,
                }}
                labelStyle={{ color: "#aaa" }}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Line
                dataKey="expectedIncome"
                name="예상 수금"
                type="monotone"
                stroke="#10b981"
                strokeWidth={2}
                dot={{ r: 2 }}
              />
              <Line
                dataKey="expectedExpense"
                name="예상 외주비"
                type="monotone"
                stroke="#ef4444"
                strokeWidth={2}
                dot={{ r: 2 }}
              />
              <Line
                dataKey="cumNet"
                name="누적 순수금"
                type="monotone"
                stroke="#6366f1"
                strokeWidth={2}
                strokeDasharray="4 4"
                dot={{ r: 2 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
