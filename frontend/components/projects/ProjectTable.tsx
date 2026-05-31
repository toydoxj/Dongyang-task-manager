"use client";

import { ProjectPopupLink } from "@/components/common/PopupLinks";
import type { ProjectTag } from "@/components/projects/ProjectCard";
import StageBadge from "@/components/ui/StageBadge";
import type { Project } from "@/lib/domain";
import { formatDate, formatPercent, formatWon } from "@/lib/format";
import { cn } from "@/lib/utils";

export type ProjectTableSortKey =
  | "code"
  | "name"
  | "stage"
  | "client"
  | "team"
  | "assignees"
  | "contract_period"
  | "amount"
  | "collection_rate";

export type ProjectSortDir = "asc" | "desc";

const TAG_LABEL: Record<ProjectTag, string> = {
  stalled: "정체",
  dueSoon: "임박",
  sealActive: "날인",
  incomeIssue: "수금",
  noAssignee: "담당미정",
  recentEdit: "최근",
};

interface Props {
  projects: Project[];
  tagsById: Map<string, ProjectTag[]>;
  sortKey?: ProjectTableSortKey | null;
  sortDir?: ProjectSortDir;
  onSortChange?: (key: ProjectTableSortKey) => void;
}

/** PROJ-003 — 카드보다 컴팩트한 테이블 보기. 한 행 click → 상세 페이지. */
export default function ProjectTable({
  projects,
  tagsById,
  sortKey = null,
  sortDir = "desc",
  onSortChange,
}: Props) {
  const thSort = { sortKey, sortDir, onSortChange };

  return (
    <div className="overflow-x-auto rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
      <table className="w-full min-w-[1040px] text-xs">
        <thead className="border-b border-zinc-200 bg-zinc-50 text-[10px] uppercase tracking-wider text-zinc-500 dark:border-zinc-800 dark:bg-zinc-950">
          <tr>
            <SortableTh k="code" label="코드" {...thSort} />
            <SortableTh k="name" label="프로젝트명" {...thSort} />
            <SortableTh k="stage" label="단계" {...thSort} />
            <SortableTh k="client" label="발주처" {...thSort} />
            <SortableTh k="team" label="담당팀" {...thSort} />
            <SortableTh k="assignees" label="담당자" {...thSort} />
            <SortableTh k="contract_period" label="계약기간" {...thSort} />
            <SortableTh k="amount" label="용역비" align="right" {...thSort} />
            <SortableTh
              k="collection_rate"
              label="수금률"
              align="right"
              {...thSort}
            />
            <th scope="col" className="px-2 py-2 text-left">
              상태 태그
            </th>
          </tr>
        </thead>
        <tbody>
          {projects.map((p) => {
            const tags = tagsById.get(p.id) ?? [];
            const rate =
              typeof p.collection_rate === "number" ? p.collection_rate : null;
            return (
              <tr
                key={p.id}
                className="border-b border-zinc-100 transition-colors hover:bg-zinc-50 dark:border-zinc-900 dark:hover:bg-zinc-800/60"
              >
                <td className="px-2 py-1.5 font-mono text-[10px] text-zinc-500">
                  <ProjectPopupLink
                    id={p.id}
                    defaultStyle={false}
                    className="hover:text-zinc-900 dark:hover:text-zinc-100"
                  >
                    {p.code || "—"}
                  </ProjectPopupLink>
                </td>
                <td className="max-w-[280px] truncate px-2 py-1.5 font-medium text-zinc-800 dark:text-zinc-200">
                  <ProjectPopupLink
                    id={p.id}
                    defaultStyle={false}
                    className="hover:underline"
                  >
                    {p.name || "(제목 없음)"}
                  </ProjectPopupLink>
                </td>
                <td className="px-2 py-1.5">
                  <StageBadge stage={p.stage} className="px-1.5" />
                </td>
                <td className="max-w-[160px] truncate px-2 py-1.5 text-zinc-700 dark:text-zinc-300">
                  {p.client_names.length > 0
                    ? p.client_names.join(", ")
                    : p.client_text || "—"}
                </td>
                <td className="px-2 py-1.5 text-zinc-700 dark:text-zinc-300">
                  {p.teams.join(", ") || "—"}
                </td>
                <td className="max-w-[140px] truncate px-2 py-1.5 text-zinc-700 dark:text-zinc-300">
                  {p.assignees.join(", ") || "—"}
                </td>
                <td className="px-2 py-1.5 font-mono text-[10px] text-zinc-500">
                  {p.contract_start
                    ? `${formatDate(p.contract_start)} ~ ${formatDate(p.contract_end)}`
                    : "—"}
                </td>
                <td className="px-2 py-1.5 text-right text-zinc-700 dark:text-zinc-300">
                  {formatWon(p.contract_amount, true)}
                </td>
                <td className="px-2 py-1.5 text-right text-zinc-700 dark:text-zinc-300">
                  {rate != null ? formatPercent(rate) : "—"}
                </td>
                <td className="px-2 py-1.5">
                  {tags.length === 0 ? (
                    <span className="text-zinc-400">—</span>
                  ) : (
                    <div className="flex flex-wrap gap-1">
                      {tags.map((t) => (
                        <span
                          key={t}
                          className="rounded bg-zinc-100 px-1 py-0.5 text-[9px] font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300"
                        >
                          {TAG_LABEL[t]}
                        </span>
                      ))}
                    </div>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {projects.length === 0 && (
        <p className="py-8 text-center text-xs text-zinc-500">
          조건에 맞는 프로젝트가 없습니다.
        </p>
      )}
    </div>
  );
}

/** 정렬 가능 header. 정렬 안 됨이면 회색 ⇅, asc=▲, desc=▼. */
function SortableTh({
  k,
  label,
  align = "left",
  sortKey,
  sortDir,
  onSortChange,
}: {
  k: ProjectTableSortKey;
  label: string;
  align?: "left" | "right";
  sortKey?: ProjectTableSortKey | null;
  sortDir?: ProjectSortDir;
  onSortChange?: (key: ProjectTableSortKey) => void;
}) {
  const active = sortKey === k;
  const arrow = active ? (sortDir === "asc" ? "▲" : "▼") : "⇅";

  return (
    <th
      scope="col"
      aria-sort={
        active ? (sortDir === "asc" ? "ascending" : "descending") : "none"
      }
      className={cn("px-2 py-2", align === "right" && "text-right")}
    >
      <button
        type="button"
        onClick={onSortChange ? () => onSortChange(k) : undefined}
        className={cn(
          "inline-flex w-full select-none items-center gap-1 whitespace-nowrap",
          align === "right" ? "justify-end" : "justify-start",
          onSortChange &&
            "cursor-pointer hover:text-zinc-700 dark:hover:text-zinc-200",
        )}
      >
        <span>{label}</span>
        <span
          className={cn(
            "text-[9px]",
            !active && "text-zinc-300 dark:text-zinc-600",
          )}
        >
          {arrow}
        </span>
      </button>
    </th>
  );
}
