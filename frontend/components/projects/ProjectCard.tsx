"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

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

// PROJ-002 — 상태 태그 (페이지에서 계산해 tags prop으로 전달).
export type ProjectTag =
  | "stalled"
  | "dueSoon"
  | "sealActive"
  | "incomeIssue"
  | "noAssignee"
  | "recentEdit";

const TAG_STYLE: Record<ProjectTag, { label: string; className: string }> = {
  stalled: {
    label: "장기 정체",
    className: "bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-300",
  },
  dueSoon: {
    label: "마감 임박",
    className: "bg-orange-100 text-orange-800 dark:bg-orange-500/20 dark:text-orange-300",
  },
  sealActive: {
    label: "날인 진행중",
    className: "bg-violet-100 text-violet-800 dark:bg-violet-500/20 dark:text-violet-300",
  },
  incomeIssue: {
    label: "수금 지연",
    className: "bg-red-100 text-red-800 dark:bg-red-500/20 dark:text-red-300",
  },
  noAssignee: {
    label: "담당 미정",
    className: "bg-zinc-200 text-zinc-700 dark:bg-zinc-700 dark:text-zinc-300",
  },
  recentEdit: {
    label: "최근 변경",
    className: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-300",
  },
};

export default function ProjectCard({
  project,
  tags = [],
}: {
  project: Project;
  tags?: ProjectTag[];
}) {
  const rateNumber =
    typeof project.collection_rate === "number"
      ? project.collection_rate
      : null;

  return (
    <Link
      href={`/projects/${project.id}`}
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

      {tags.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {tags.map((t) => (
            <span
              key={t}
              className={cn(
                "rounded px-1.5 py-0.5 text-[10px] font-medium leading-none",
                TAG_STYLE[t].className,
              )}
            >
              {TAG_STYLE[t].label}
            </span>
          ))}
        </div>
      )}

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

      {/* PROJ-004 — 카드 quick action: 본문 click(상세)과 별개로 특정 영역으로 이동 */}
      <div className="mt-3 flex flex-wrap gap-1 border-t border-zinc-100 pt-2 dark:border-zinc-800">
        <QuickActionChip
          label="TASK"
          href={`/projects/${project.id}#tasks`}
        />
        <QuickActionChip
          label="날인"
          href={`/seal-requests?project_id=${project.id}`}
        />
        <QuickActionChip
          label="매출"
          href={`/projects/${project.id}#cashflow`}
        />
        {project.url && (
          <QuickActionChip label="노션" href={project.url} external />
        )}
      </div>
    </Link>
  );
}

/** 카드 본문 Link 안에서 nested anchor 회피용 — button + stopPropagation + 직접 navigate. */
function QuickActionChip({
  label,
  href,
  external = false,
}: {
  label: string;
  href: string;
  external?: boolean;
}) {
  const router = useRouter();
  return (
    <button
      type="button"
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        if (external) window.open(href, "_blank", "noopener,noreferrer");
        else router.push(href);
      }}
      className="rounded border border-zinc-300 bg-white px-1.5 py-0.5 text-[10px] font-medium text-zinc-600 hover:bg-zinc-100 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800"
    >
      {label}
    </button>
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
