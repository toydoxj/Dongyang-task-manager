"use client";

/**
 * 주간 업무일지 — 대기/보류 프로젝트 표 (자체 2-col 분할).
 * PR-AI — app/weekly-report/page.tsx에서 추출.
 */

import type { WeeklyStageProject } from "@/lib/api";
import { cn } from "@/lib/utils";

import { ProjectLink } from "./links";

/** 대기/보류 프로젝트를 절반씩 자체 2-col grid로 분할. */
export function SplitStageGrid({
  rows,
  highlightStalled,
}: {
  rows: WeeklyStageProject[];
  highlightStalled?: boolean;
}) {
  if (rows.length === 0) {
    return (
      <div className="rounded border border-dashed border-zinc-300 px-3 py-2 text-center text-xs italic text-zinc-400 dark:border-zinc-700">
        (없음)
      </div>
    );
  }
  const half = Math.ceil(rows.length / 2);
  const left = rows.slice(0, half);
  const right = rows.slice(half);
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <StageProjectsTable rows={left} highlightStalled={highlightStalled} />
      {right.length > 0 && (
        <StageProjectsTable rows={right} highlightStalled={highlightStalled} />
      )}
    </div>
  );
}

/** 대기/보류 프로젝트 표 — 4컬럼 단순화 + 3개월 이상 대기는 용역명 짙은 빨강. */
export function StageProjectsTable({
  rows,
  highlightStalled,
}: {
  rows: WeeklyStageProject[];
  highlightStalled?: boolean;
}) {
  if (rows.length === 0) {
    return (
      <div className="rounded border border-dashed border-zinc-300 px-3 py-2 text-center text-xs italic text-zinc-400 dark:border-zinc-700">
        (없음)
      </div>
    );
  }
  return (
    <div className="overflow-x-auto rounded border border-zinc-200 dark:border-zinc-800">
      <table className="w-full border-collapse text-xs">
        <thead className="bg-zinc-100 dark:bg-zinc-900">
          <tr>
            {["CODE", "용역명", "발주처", "담당팀"].map((c) => (
              <th
                key={c}
                className="border-b border-zinc-200 px-2 py-1.5 text-left font-medium dark:border-zinc-800"
              >
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr
              key={i}
              className="border-b border-zinc-100 last:border-0 dark:border-zinc-800"
            >
              <td className="px-2 py-1 align-top">{r.code}</td>
              <td
                className={cn(
                  "px-2 py-1 align-top",
                  highlightStalled &&
                    r.is_long_stalled &&
                    "font-semibold text-red-700 dark:text-red-400",
                )}
                title={
                  highlightStalled && r.is_long_stalled
                    ? "3개월 이상 대기 — 활동 점검 필요"
                    : undefined
                }
              >
                <ProjectLink id={r.page_id}>{r.name}</ProjectLink>
              </td>
              <td className="px-2 py-1 align-top">{r.client}</td>
              <td className="px-2 py-1 align-top">{r.teams.join(", ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
