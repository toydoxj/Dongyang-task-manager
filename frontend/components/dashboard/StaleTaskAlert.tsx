"use client";

import Link from "next/link";

import type { Task } from "@/lib/domain";
import { dDayLabel, formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

interface Props {
  tasks: Task[];
  topN?: number;
}

function daysSince(iso: string | null): number | null {
  if (!iso) return null;
  return Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
}

export default function StaleTaskAlert({ tasks, topN = 10 }: Props) {
  // status === '시작 전' 만, 생성일 오래된 순
  const stale = tasks
    .filter((t) => t.status === "시작 전")
    .sort((a, b) => {
      const ad = a.created_time ?? "";
      const bd = b.created_time ?? "";
      return ad.localeCompare(bd); // 오래된 순
    })
    .slice(0, topN);

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <header className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">시작 전 TASK 적체</h3>
          <p className="text-[10px] text-zinc-500">
            생성된 지 오래되었지만 아직 착수되지 않은 업무 Top {topN}
          </p>
        </div>
        <span className="text-xs text-zinc-500">
          {tasks.filter((t) => t.status === "시작 전").length}건 전체
        </span>
      </header>

      {stale.length === 0 ? (
        <p className="py-6 text-center text-xs text-zinc-500">
          시작 전 상태의 TASK가 없습니다. 🎉
        </p>
      ) : (
        <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
          {stale.map((t) => {
            const since = daysSince(t.created_time);
            const projId = t.project_ids[0];
            const node = (
              <div className="flex items-center justify-between gap-3 px-1 py-2">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium" title={t.title}>
                    {t.title || "(제목 없음)"}
                  </p>
                  <p className="mt-0.5 text-[11px] text-zinc-500">
                    생성 {formatDate(t.created_time)} · 마감 {formatDate(t.end_date)}
                    {t.assignees.length > 0 && (
                      <> · {t.assignees.slice(0, 2).join(", ")}{t.assignees.length > 2 && ` +${t.assignees.length - 2}`}</>
                    )}
                  </p>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-0.5">
                  <span
                    className={cn(
                      "rounded-md px-2 py-0.5 text-[10px] font-medium",
                      since != null && since >= 30
                        ? "bg-red-500/20 text-red-400"
                        : since != null && since >= 14
                          ? "bg-orange-500/20 text-orange-400"
                          : "bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
                    )}
                  >
                    {since != null ? `+${since}일` : "—"}
                  </span>
                  {t.end_date && (
                    <span className="text-[9px] text-zinc-500">
                      {dDayLabel(t.end_date)}
                    </span>
                  )}
                </div>
              </div>
            );
            return (
              <li key={t.id}>
                {projId ? (
                  <Link
                    href={`/projects/${projId}`}
                    className="block rounded-md hover:bg-zinc-50 dark:hover:bg-zinc-800/50"
                  >
                    {node}
                  </Link>
                ) : (
                  node
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
