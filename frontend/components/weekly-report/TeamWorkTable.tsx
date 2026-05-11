"use client";

/**
 * 주간 업무일지 — 팀별 업무 현황 표.
 * 같은 직원의 첫 row만 이름/직책 표시 (rowspan 효과).
 * PR-AI — app/weekly-report/page.tsx에서 추출.
 */

import type { WeeklyEmployeeWorkRow } from "@/lib/api";

import { ProjectLink, SaleLink } from "./links";

export function TeamWorkTable({
  team,
  rows,
}: {
  team: string;
  rows: WeeklyEmployeeWorkRow[];
}) {
  // 같은 직원 연속 row를 찾아 첫 번째에만 이름 표시 + rowspan 카운트
  const renderRows = rows.map((r, i) => {
    const prev = i > 0 ? rows[i - 1] : null;
    const isFirst = !prev || prev.employee_name !== r.employee_name;
    let rowspan = 1;
    if (isFirst) {
      for (let j = i + 1; j < rows.length; j++) {
        if (rows[j].employee_name === r.employee_name) rowspan++;
        else break;
      }
    }
    return { row: r, isFirst, rowspan };
  });

  return (
    <div>
      <h3 className="mb-1 text-sm font-semibold">
        {team}{" "}
        <span className="text-xs font-normal text-zinc-500">
          ({rows.length}건)
        </span>
      </h3>
      <div className="overflow-x-auto rounded border border-zinc-200 dark:border-zinc-800">
        <table className="w-full border-collapse text-xs">
          <thead className="bg-zinc-100 dark:bg-zinc-900">
            <tr>
              <th className="border-b border-r border-zinc-200 px-2 py-1.5 text-left font-medium dark:border-zinc-800">
                담당자
              </th>
              <th className="border-b border-r border-zinc-200 px-2 py-1.5 text-left font-medium dark:border-zinc-800">
                CODE
              </th>
              <th className="border-b border-r border-zinc-200 px-2 py-1.5 text-left font-medium dark:border-zinc-800">
                PROJECT
              </th>
              <th className="border-b border-r border-zinc-200 px-2 py-1.5 text-left font-medium dark:border-zinc-800">
                발주처
              </th>
              <th className="border-b border-r border-zinc-200 px-2 py-1.5 text-left font-medium dark:border-zinc-800">
                진행단계
              </th>
              <th className="border-b border-r border-zinc-200 px-2 py-1.5 text-left font-medium dark:border-zinc-800">
                지난주 업무
              </th>
              <th className="border-b border-zinc-200 px-2 py-1.5 text-left font-medium dark:border-zinc-800">
                이번주 업무
              </th>
            </tr>
          </thead>
          <tbody>
            {renderRows.map(({ row, isFirst, rowspan }, i) => {
              const isLastOfGroup =
                i === renderRows.length - 1 ||
                renderRows[i + 1].isFirst;
              const rowBorder = isLastOfGroup
                ? "border-b border-zinc-300 dark:border-zinc-700"
                : "border-b border-zinc-100 dark:border-zinc-800/60";
              return (
                <tr key={i} className={rowBorder}>
                  {isFirst && (
                    <td
                      rowSpan={rowspan}
                      className="border-r border-zinc-200 bg-zinc-50 px-2 py-1 align-top font-medium dark:border-zinc-800 dark:bg-zinc-900/40"
                    >
                      {row.employee_name}
                      {row.position && (
                        <>
                          <br />
                          <span className="text-[10px] font-normal text-zinc-500">
                            {row.position}
                          </span>
                        </>
                      )}
                    </td>
                  )}
                  <td className="border-r border-zinc-200 px-2 py-1 align-top dark:border-zinc-800">
                    {row.project_code}
                  </td>
                  <td className="border-r border-zinc-200 px-2 py-1 align-top dark:border-zinc-800">
                    {row.kind === "sale" ? (
                      <SaleLink id={row.source_id}>{row.project_name}</SaleLink>
                    ) : (
                      <ProjectLink id={row.source_id}>{row.project_name}</ProjectLink>
                    )}
                  </td>
                  <td className="border-r border-zinc-200 px-2 py-1 align-top dark:border-zinc-800">
                    {row.client}
                  </td>
                  <td className="border-r border-zinc-200 px-2 py-1 align-top dark:border-zinc-800">
                    {row.phase || row.stage}
                  </td>
                  <td className="border-r border-zinc-200 px-2 py-1 align-top text-zinc-600 dark:border-zinc-800 dark:text-zinc-400">
                    {row.last_week_summary || "—"}
                  </td>
                  <td className="px-2 py-1 align-top">
                    {row.this_week_plan || "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
