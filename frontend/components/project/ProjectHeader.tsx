"use client";

import type { Project } from "@/lib/domain";
import { formatDate } from "@/lib/format";
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

export default function ProjectHeader({ project }: { project: Project }) {
  return (
    <header className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="font-mono text-xs text-zinc-500">
            {project.code || "—"}
            {project.master_code && (
              <span className="ml-2 text-zinc-400">({project.master_code})</span>
            )}
          </p>
          <h1 className="mt-1 text-xl font-semibold text-zinc-900 dark:text-zinc-100">
            {project.name || "(제목 없음)"}
          </h1>
          <p className="mt-1 text-sm text-zinc-500">
            발주처: {project.client_text || "—"}
          </p>
        </div>

        {project.stage && (
          <span
            className={cn(
              "rounded-md border px-3 py-1 text-xs font-medium",
              STAGE_BADGE[project.stage] ??
                "border-zinc-500/30 bg-zinc-500/15 text-zinc-400",
            )}
          >
            {project.stage}
          </span>
        )}
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-xs md:grid-cols-4">
        <Field label="담당팀" value={project.teams.join(", ") || "—"} />
        <Field label="담당자" value={project.assignees.join(", ") || "—"} />
        <Field label="업무내용" value={project.work_types.join(", ") || "—"} />
        <Field label="계약" value={project.contract_signed ? "✓" : "미체결"} />
        <Field label="수주일" value={formatDate(project.start_date)} />
        <Field
          label="계약기간"
          value={
            project.contract_start
              ? `${formatDate(project.contract_start)} ~ ${formatDate(project.contract_end)}`
              : "—"
          }
        />
        <Field label="완료일" value={formatDate(project.end_date)} />
        <Field
          label="수정일"
          value={formatDate(project.last_edited_time)}
        />
      </dl>
    </header>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-zinc-500">{label}</dt>
      <dd className="mt-0.5 truncate text-zinc-800 dark:text-zinc-200" title={value}>
        {value}
      </dd>
    </div>
  );
}
