"use client";

import { ResponsiveHeatMap } from "@nivo/heatmap";

import type { Project } from "@/lib/domain";
import { TEAMS } from "@/lib/domain";

interface Props {
  projects: Project[];
  monthsBack?: number;
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
  // monthKey = "YY-MM" → 그 달 1일~말일
  const [yy, mm] = monthKey.split("-").map(Number);
  const year = 2000 + yy;
  const monthStart = new Date(year, mm - 1, 1);
  const monthEnd = new Date(year, mm, 0);
  const s = start ? new Date(start) : null;
  const e = end ? new Date(end) : null;
  if (!s) return false;
  // [s, e] 와 [monthStart, monthEnd] 겹침
  if (e == null) {
    return s <= monthEnd; // 종료일 미정 → 시작 후 모든 월
  }
  return s <= monthEnd && e >= monthStart;
}

function buildData(projects: Project[], monthsBack: number): Row[] {
  const months = buildMonths(monthsBack);
  return TEAMS.map((team): Row => {
    const data: Cell[] = months.map((m) => {
      let count = 0;
      for (const p of projects) {
        if (p.completed) continue;
        if (!p.teams.includes(team)) continue;
        const start = p.contract_start ?? p.start_date;
        const end = p.contract_end ?? p.end_date;
        if (isOverlap(start, end, m)) count += 1;
      }
      return { x: m, y: count };
    });
    return { id: team, data };
  });
}

export default function TeamLoadHeatmap({ projects, monthsBack = 12 }: Props) {
  const data = buildData(projects, monthsBack);
  const isDark =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
  const axisColor = isDark ? "#a1a1aa" : "#52525b";

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <header className="mb-3">
        <h3 className="text-sm font-semibold">팀별 부하 히트맵</h3>
        <p className="text-[10px] text-zinc-500">
          담당팀 × 월별 동시 진행 프로젝트 수 (계약기간 기준, 최근 {monthsBack}개월)
        </p>
      </header>

      <div className="h-72">
        <ResponsiveHeatMap
          data={data}
          margin={{ top: 10, right: 10, bottom: 30, left: 80 }}
          axisTop={null}
          axisRight={null}
          axisBottom={{
            tickSize: 4,
            tickPadding: 5,
            tickRotation: 0,
          }}
          axisLeft={{
            tickSize: 4,
            tickPadding: 5,
            tickRotation: 0,
          }}
          colors={{
            type: "sequential",
            scheme: "blues",
          }}
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
