"use client";

import Link from "next/link";

import type { ProjectTag } from "@/components/projects/ProjectCard";
import StageBadge from "@/components/ui/StageBadge";
import type { Project } from "@/lib/domain";
import { formatDate, formatPercent, formatWon } from "@/lib/format";

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
}

/** PROJ-003 — 카드보다 컴팩트한 테이블 보기. 한 행 click → 상세 페이지. */
export default function ProjectTable({ projects, tagsById }: Props) {
  return (
    <div className="overflow-x-auto rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
      <table className="w-full text-xs">
        <thead className="border-b border-zinc-200 bg-zinc-50 text-[10px] uppercase tracking-wider text-zinc-500 dark:border-zinc-800 dark:bg-zinc-950">
          <tr>
            <th className="px-2 py-2 text-left">코드</th>
            <th className="px-2 py-2 text-left">프로젝트명</th>
            <th className="px-2 py-2 text-left">단계</th>
            <th className="px-2 py-2 text-left">발주처</th>
            <th className="px-2 py-2 text-left">담당팀</th>
            <th className="px-2 py-2 text-left">담당자</th>
            <th className="px-2 py-2 text-left">계약기간</th>
            <th className="px-2 py-2 text-right">용역비</th>
            <th className="px-2 py-2 text-right">수금률</th>
            <th className="px-2 py-2 text-left">상태 태그</th>
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
                  <Link
                    href={`/projects/${p.id}`}
                    className="hover:text-zinc-900 dark:hover:text-zinc-100"
                  >
                    {p.code || "—"}
                  </Link>
                </td>
                <td className="max-w-[280px] truncate px-2 py-1.5 font-medium text-zinc-800 dark:text-zinc-200">
                  <Link
                    href={`/projects/${p.id}`}
                    className="hover:underline"
                    title={p.name}
                  >
                    {p.name || "(제목 없음)"}
                  </Link>
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
