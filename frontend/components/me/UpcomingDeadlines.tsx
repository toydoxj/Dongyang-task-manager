"use client";

import Link from "next/link";

import type { Project } from "@/lib/domain";
import { dDayLabel, formatDate, formatPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

interface Props {
  projects: Project[];
  topN?: number;
}

function pickDeadline(p: Project): string | null {
  return p.contract_end ?? p.end_date ?? null;
}

function daysToNow(iso: string | null): number | null {
  if (!iso) return null;
  return Math.floor((new Date(iso).getTime() - Date.now()) / 86400000);
}

export default function UpcomingDeadlines({ projects, topN = 10 }: Props) {
  // 완료/타절/종결 제외, 마감일 가까운 순 정렬
  const open = projects
    .filter((p) => !p.completed && !["완료", "타절", "종결"].includes(p.stage))
    .map((p) => ({ p, due: pickDeadline(p) }))
    .filter((x) => x.due != null)
    .sort((a, b) => (a.due as string).localeCompare(b.due as string))
    .slice(0, topN);

  if (open.length === 0) {
    return (
      <p className="rounded-md border border-zinc-200 bg-white p-4 text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900">
        마감일이 등록된 진행 프로젝트가 없습니다.
      </p>
    );
  }

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900">
      <ul className="space-y-1">
        {open.map(({ p, due }) => {
          const days = daysToNow(due);
          const rate =
            typeof p.collection_rate === "number" ? p.collection_rate : null;
          return (
            <li key={p.id}>
              <Link
                href={`/project?id=${p.id}`}
                className="flex items-center justify-between gap-3 rounded-md px-2 py-2 hover:bg-zinc-50 dark:hover:bg-zinc-800/50"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium" title={p.name}>
                    {p.name || "(제목 없음)"}
                  </p>
                  <p className="mt-0.5 text-[11px] text-zinc-500">
                    {p.code} · {p.stage || "—"} · 수금률 {formatPercent(rate)}
                  </p>
                </div>
                <div className="flex shrink-0 flex-col items-end">
                  <span
                    className={cn(
                      "rounded-md px-2 py-0.5 text-[10px] font-medium",
                      days == null
                        ? "bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
                        : days < 0
                          ? "bg-red-500/20 text-red-400"
                          : days <= 7
                            ? "bg-orange-500/20 text-orange-400"
                            : days <= 30
                              ? "bg-yellow-500/20 text-yellow-400"
                              : "bg-emerald-500/20 text-emerald-400",
                    )}
                  >
                    {dDayLabel(due)}
                  </span>
                  <span className="mt-0.5 text-[9px] text-zinc-500">
                    {formatDate(due)}
                  </span>
                </div>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
