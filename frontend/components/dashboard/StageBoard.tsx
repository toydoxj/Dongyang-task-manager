"use client";

import Link from "next/link";

import type { Project } from "@/lib/domain";
import { PROJECT_STAGES } from "@/lib/domain";
import { formatWon } from "@/lib/format";
import { cn } from "@/lib/utils";

interface Props {
  projects: Project[];
}

const STAGE_COLOR: Record<string, string> = {
  "진행중": "border-blue-500/40 bg-blue-500/5",
  "대기": "border-purple-500/40 bg-purple-500/5",
  "보류": "border-pink-500/40 bg-pink-500/5",
  "완료": "border-emerald-500/40 bg-emerald-500/5",
  "타절": "border-red-500/40 bg-red-500/5",
  "종결": "border-zinc-500/40 bg-zinc-500/5",
  "이관": "border-zinc-400/30 bg-zinc-400/5",
};

const STAGE_DOT: Record<string, string> = {
  "진행중": "bg-blue-500",
  "대기": "bg-purple-500",
  "보류": "bg-pink-500",
  "완료": "bg-emerald-500",
  "타절": "bg-red-500",
  "종결": "bg-zinc-500",
  "이관": "bg-zinc-400",
};

export default function StageBoard({ projects }: Props) {
  const grouped = new Map<string, Project[]>();
  for (const stage of PROJECT_STAGES) grouped.set(stage, []);
  for (const p of projects) {
    const list = grouped.get(p.stage);
    if (list) list.push(p);
  }

  return (
    <div className="flex gap-3 overflow-x-auto pb-2">
      {PROJECT_STAGES.map((stage) => {
        const items = grouped.get(stage) ?? [];
        const total = items.reduce((s, p) => s + (p.contract_amount ?? 0), 0);
        return (
          <div
            key={stage}
            className={cn(
              "flex w-72 flex-shrink-0 flex-col rounded-xl border bg-white dark:bg-zinc-900",
              STAGE_COLOR[stage] ?? "border-zinc-300",
            )}
          >
            <header className="flex items-center justify-between border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
              <div className="flex items-center gap-2">
                <span className={cn("h-2 w-2 rounded-full", STAGE_DOT[stage])} />
                <h3 className="text-sm font-semibold">{stage}</h3>
                <span className="text-xs text-zinc-500">{items.length}건</span>
              </div>
              <span className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
                {formatWon(total, true)}
              </span>
            </header>

            <ul className="max-h-[480px] space-y-1.5 overflow-y-auto p-2">
              {items.length === 0 && (
                <li className="px-2 py-6 text-center text-xs text-zinc-400">
                  비어있음
                </li>
              )}
              {items.slice(0, 50).map((p) => (
                <li key={p.id}>
                  <Link
                    href={`/project?id=${p.id}`}
                    className="block rounded-md border border-zinc-200 bg-white p-2.5 text-xs transition-colors hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950 dark:hover:bg-zinc-900"
                  >
                    <p className="font-medium text-zinc-900 dark:text-zinc-100 truncate">
                      {p.name || "(제목 없음)"}
                    </p>
                    <div className="mt-1 flex items-center justify-between">
                      <span className="font-mono text-[10px] text-zinc-500">
                        {p.code || "—"}
                      </span>
                      <span className="text-[10px] text-zinc-500">
                        {p.assignees.length > 0
                          ? p.assignees.length === 1
                            ? p.assignees[0]
                            : `${p.assignees[0]} +${p.assignees.length - 1}`
                          : "—"}
                      </span>
                    </div>
                  </Link>
                </li>
              ))}
              {items.length > 50 && (
                <li className="px-2 py-2 text-center text-[10px] text-zinc-400">
                  … {items.length - 50}건 더
                </li>
              )}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
