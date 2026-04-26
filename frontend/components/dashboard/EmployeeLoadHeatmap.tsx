"use client";

import { ResponsiveHeatMap } from "@nivo/heatmap";

import type { Project } from "@/lib/domain";

interface Props {
  projects: Project[];
  monthsBack?: number;
  /** 부하 많은 상위 N명만 (기본 20). 0이면 전원. */
  topN?: number;
}

interface Cell {
  x: string;
  y: number;
}

interface Row {
  id: string;
  data: Cell[];
}

function buildMonths(monthsBack: number): string[] {
  const now = new Date();
  const out: string[] = [];
  for (let i = monthsBack - 1; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    out.push(`${String(d.getFullYear()).slice(2)}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  }
  return out;
}

function isOverlap(start: string | null, end: string | null, monthKey: string): boolean {
  const [yy, mm] = monthKey.split("-").map(Number);
  const year = 2000 + yy;
  const monthStart = new Date(year, mm - 1, 1);
  const monthEnd = new Date(year, mm, 0);
  const s = start ? new Date(start) : null;
  const e = end ? new Date(end) : null;
  if (!s) return false;
  if (e == null) return s <= monthEnd;
  return s <= monthEnd && e >= monthStart;
}

function buildData(projects: Project[], monthsBack: number, topN: number): Row[] {
  const months = buildMonths(monthsBack);

  // 진행 중인 프로젝트의 assignees union
  const assigneeSet = new Set<string>();
  for (const p of projects) {
    if (p.completed) continue;
    for (const a of p.assignees) {
      if (a.trim()) assigneeSet.add(a);
    }
  }

  // 각 직원 × 월별 동시 진행 프로젝트 수
  const rowsAll = Array.from(assigneeSet).map((person): Row => {
    const data: Cell[] = months.map((m) => {
      let count = 0;
      for (const p of projects) {
        if (p.completed) continue;
        if (!p.assignees.includes(person)) continue;
        const start = p.contract_start ?? p.start_date;
        const end = p.contract_end ?? p.end_date;
        if (isOverlap(start, end, m)) count += 1;
      }
      return { x: m, y: count };
    });
    return { id: person, data };
  });

  // 총 부하(합계) 기준 내림차순 → 상위 N명
  rowsAll.sort((a, b) => {
    const sumA = a.data.reduce((s, c) => s + c.y, 0);
    const sumB = b.data.reduce((s, c) => s + c.y, 0);
    return sumB - sumA;
  });
  return topN > 0 ? rowsAll.slice(0, topN) : rowsAll;
}

export default function EmployeeLoadHeatmap({
  projects,
  monthsBack = 12,
  topN = 20,
}: Props) {
  const data = buildData(projects, monthsBack, topN);
  const isDark =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
  const axisColor = isDark ? "#a1a1aa" : "#52525b";

  if (data.length === 0) {
    return (
      <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
        <h3 className="text-sm font-semibold">직원별 부하 히트맵</h3>
        <p className="mt-3 text-xs text-zinc-500">진행 중인 프로젝트가 없습니다.</p>
      </div>
    );
  }

  // 직원 수에 따라 차트 높이 동적 (행당 22px + 여백)
  const chartHeight = Math.max(220, data.length * 22 + 40);

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <header className="mb-3">
        <h3 className="text-sm font-semibold">직원별 부하 히트맵</h3>
        <p className="text-[10px] text-zinc-500">
          담당자 × 월별 동시 진행 프로젝트 수 (계약기간 기준, 최근 {monthsBack}개월
          {topN > 0 && data.length >= topN ? ` · 상위 ${topN}명` : ""})
        </p>
      </header>

      <div style={{ height: chartHeight }}>
        <ResponsiveHeatMap
          data={data}
          margin={{ top: 10, right: 10, bottom: 30, left: 80 }}
          axisTop={null}
          axisRight={null}
          axisBottom={{ tickSize: 4, tickPadding: 5, tickRotation: 0 }}
          axisLeft={{ tickSize: 4, tickPadding: 5, tickRotation: 0 }}
          colors={{ type: "sequential", scheme: "purples" }}
          emptyColor={isDark ? "#27272a" : "#f4f4f5"}
          borderColor={isDark ? "#18181b" : "#fafafa"}
          borderWidth={2}
          labelTextColor={isDark ? "#fafafa" : "#18181b"}
          theme={{
            text: { fill: axisColor, fontSize: 12, fontWeight: 500 },
            axis: {
              ticks: { text: { fill: axisColor, fontSize: 12, fontWeight: 500 } },
            },
            labels: { text: { fontSize: 12, fontWeight: 600 } },
            tooltip: {
              container: {
                background: "rgba(20,20,20,0.92)",
                color: "#e4e4e7",
                fontSize: 12,
              },
            },
          }}
        />
      </div>
    </div>
  );
}
