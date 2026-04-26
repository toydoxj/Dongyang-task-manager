"use client";

import Link from "next/link";

import type { Project } from "@/lib/domain";
import { formatDate, formatPercent, formatWon } from "@/lib/format";
import { cn } from "@/lib/utils";

const STAGE_BADGE: Record<string, string> = {
  "진행중": "bg-blue-500/15 text-blue-400 border-blue-500/30",
  "대기": "bg-purple-500/15 text-purple-400 border-purple-500/30",
  "보류": "bg-pink-500/15 text-pink-400 border-pink-500/30",
  "완료": "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  "타절": "bg-red-500/15 text-red-400 border-red-500/30",
  "종결": "bg-zinc-500/15 text-zinc-400 border-zinc-500/30",
  "이관": "bg-zinc-400/15 text-zinc-400 border-zinc-400/30",
};

export default function ProjectCard({ project }: { project: Project }) {
  const rateNumber =
    typeof project.collection_rate === "number"
      ? project.collection_rate
      : null;

  return (
    <Link
      href={`/project?id=${project.id}`}
      className="group block rounded-xl border border-zinc-200 bg-white p-4 transition-colors hover:border-zinc-300 hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:border-zinc-700 dark:hover:bg-zinc-800"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="font-mono text-[10px] text-zinc-500">
            {project.code || "—"}
          </p>
          <h3 className="mt-0.5 truncate text-sm font-semibold text-zinc-900 dark:text-zinc-100">
            {project.name || "(제목 없음)"}
          </h3>
        </div>
        {project.stage && (
          <span
            className={cn(
              "rounded-md border px-2 py-0.5 text-[10px] font-medium",
              STAGE_BADGE[project.stage] ??
                "border-zinc-500/30 bg-zinc-500/15 text-zinc-400",
            )}
          >
            {project.stage}
          </span>
        )}
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1.5 text-[11px]">
        <Row
          label="발주처"
          value={
            project.client_names.length > 0
              ? project.client_names.join(", ")
              : project.client_text || "—"
          }
        />
        <Row label="담당팀" value={project.teams.join(", ") || "—"} />
        <Row label="담당자" value={project.assignees.join(", ") || "—"} />
        <Row
          label="계약기간"
          value={
            project.contract_start
              ? `${formatDate(project.contract_start)} ~ ${formatDate(project.contract_end)}`
              : "—"
          }
        />
        <Row label="용역비" value={formatWon(project.contract_amount, true)} />
        {rateNumber != null && (
          <Row label="수금률" value={formatPercent(rateNumber)} />
        )}
      </dl>
    </Link>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="text-zinc-500">{label}</dt>
      <dd className="truncate text-right text-zinc-700 dark:text-zinc-300">
        {value}
      </dd>
    </>
  );
}
