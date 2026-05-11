"use client";

/**
 * 주간 업무일지 — 개인 주간 일정 카드 + mini 표 + helpers.
 * PR-AH — app/weekly-report/page.tsx에서 추출 (외과적 변경 / 동작 동일).
 */

import type {
  WeeklyHoliday,
  WeeklyPersonalScheduleEntry,
  WeeklyTeamMember,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const SCHEDULE_KIND_STYLE: Record<string, string> = {
  project: "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300",
  sale: "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300",
  other: "bg-zinc-200 text-zinc-700 dark:bg-zinc-700 dark:text-zinc-200",
};

/** 직원 단위 일정 lookup: {employee_name: [day0..day4 entries]}. team 무관 — team_members로 분류. */
export function buildScheduleByEmployee(
  entries: WeeklyPersonalScheduleEntry[],
  weekStart: string,
  weekEnd: string,
): Record<string, WeeklyPersonalScheduleEntry[][]> {
  const start = new Date(`${weekStart}T00:00:00`);
  const end = new Date(`${weekEnd}T00:00:00`);
  const dayCount = Math.max(
    1,
    Math.round((end.getTime() - start.getTime()) / 86_400_000) + 1,
  );
  const result: Record<string, WeeklyPersonalScheduleEntry[][]> = {};
  for (const e of entries) {
    const sd = new Date(`${e.start_date}T00:00:00`);
    const ed = new Date(`${e.end_date}T00:00:00`);
    if (Number.isNaN(sd.getTime()) || Number.isNaN(ed.getTime())) continue;
    if (!result[e.employee_name]) {
      result[e.employee_name] = Array.from({ length: dayCount }, () => []);
    }
    for (let i = 0; i < dayCount; i++) {
      const day = new Date(start);
      day.setDate(start.getDate() + i);
      if (sd <= day && day <= ed) result[e.employee_name][i].push(e);
    }
  }
  return result;
}

/** 주차 시작/종료에 맞는 요일 라벨 + 날짜 list 생성. 5일 고정이 아니라 가변 길이. */
export function buildWeekDays(
  weekStart: string,
  weekEnd: string,
): { iso: string; label: string }[] {
  const KOR = ["일", "월", "화", "수", "목", "금", "토"];
  const start = new Date(`${weekStart}T00:00:00`);
  const end = new Date(`${weekEnd}T00:00:00`);
  const days: { iso: string; label: string }[] = [];
  const cur = new Date(start);
  while (cur <= end) {
    const y = cur.getFullYear();
    const m = String(cur.getMonth() + 1).padStart(2, "0");
    const d = String(cur.getDate()).padStart(2, "0");
    days.push({ iso: `${y}-${m}-${d}`, label: KOR[cur.getDay()] });
    cur.setDate(cur.getDate() + 1);
  }
  return days;
}

interface ScheduleTeamCardProps {
  team: string;
  members: WeeklyTeamMember[];
  scheduleByEmployee: Record<string, WeeklyPersonalScheduleEntry[][]>;
  weekDays: { iso: string; label: string }[];
  holidayByIso: Record<string, WeeklyHoliday[]>;
  /** 진단팀 column에만 — 본부 직원을 같은 카드 아래에 stack 표시. */
  extra?: { title: string; members: WeeklyTeamMember[] };
}

export function ScheduleTeamCard({
  team,
  members,
  scheduleByEmployee,
  weekDays,
  holidayByIso,
  extra,
}: ScheduleTeamCardProps) {
  return (
    <div className="rounded border border-zinc-200 bg-white text-[10.5px] dark:border-zinc-800 dark:bg-zinc-950">
      <div className="border-b border-zinc-200 bg-zinc-100 px-2 py-1 text-xs font-semibold dark:border-zinc-800 dark:bg-zinc-900">
        {team}{" "}
        <span className="font-normal text-zinc-500">({members.length}명)</span>
      </div>
      <ScheduleMiniTable
        members={members}
        scheduleByEmployee={scheduleByEmployee}
        weekDays={weekDays}
        holidayByIso={holidayByIso}
      />
      {extra && extra.members.length > 0 && (
        <>
          <div className="border-t border-b border-zinc-200 bg-zinc-100 px-2 py-1 text-xs font-semibold dark:border-zinc-800 dark:bg-zinc-900">
            {extra.title}{" "}
            <span className="font-normal text-zinc-500">
              ({extra.members.length}명)
            </span>
          </div>
          <ScheduleMiniTable
            members={extra.members}
            scheduleByEmployee={scheduleByEmployee}
            weekDays={weekDays}
            holidayByIso={holidayByIso}
          />
        </>
      )}
    </div>
  );
}

export function ScheduleMiniTable({
  members,
  scheduleByEmployee,
  weekDays,
  holidayByIso,
}: {
  members: WeeklyTeamMember[];
  scheduleByEmployee: Record<string, WeeklyPersonalScheduleEntry[][]>;
  weekDays: { iso: string; label: string }[];
  holidayByIso: Record<string, WeeklyHoliday[]>;
}) {
  if (members.length === 0) {
    return (
      <div className="px-2 py-3 text-center text-[10px] italic text-zinc-400">
        (팀원 없음)
      </div>
    );
  }
  return (
    // table-fixed로 컬럼 폭 강제 — 담당자 컴팩트, 월~금이 충분히 넓음
    <table className="w-full table-fixed border-collapse">
      <colgroup>
        <col style={{ width: "30%" }} />
        {weekDays.map((d) => (
          <col key={d.iso} style={{ width: `${70 / weekDays.length}%` }} />
        ))}
      </colgroup>
      <thead className="bg-zinc-50 dark:bg-zinc-900/60">
        <tr>
          <th className="border-b border-zinc-200 px-1.5 py-0.5 text-left font-medium dark:border-zinc-800">
            담당자
          </th>
          {weekDays.map((d) => {
            const h = holidayByIso[d.iso];
            return (
              <th
                key={d.iso}
                title={h?.map((x) => x.name).join(", ")}
                className={cn(
                  "border-b border-l border-zinc-200 px-0 py-0.5 text-center font-medium dark:border-zinc-800",
                  h && "bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300",
                )}
              >
                {d.label}
              </th>
            );
          })}
        </tr>
      </thead>
      <tbody>
        {members.map((m) => {
          const days = scheduleByEmployee[m.name] ?? [];
          return (
            <tr
              key={m.name}
              className="border-b border-zinc-100 last:border-0 dark:border-zinc-800/60"
            >
              <td className="px-1.5 py-0.5 align-top">
                <div className="font-medium leading-tight">{m.name}</div>
                {m.position && (
                  <div className="text-[9px] leading-tight text-zinc-500">
                    {m.position}
                  </div>
                )}
              </td>
              {weekDays.map((d, i) => {
                const cells = days[i] ?? [];
                const isHoliday = !!holidayByIso[d.iso];
                return (
                  <td
                    key={d.iso}
                    className={cn(
                      "border-l border-zinc-100 px-0 py-0.5 text-center align-middle dark:border-zinc-800/60",
                      isHoliday &&
                        "bg-red-50/50 dark:bg-red-950/20",
                    )}
                  >
                    {cells.map((c, j) => (
                      <span
                        key={j}
                        title={`${c.category}${c.project_code ? ` · ${c.project_code}` : ""}`}
                        className={cn(
                          "mx-0.5 inline-block rounded px-1 py-0.5 text-[9px] font-medium leading-tight",
                          SCHEDULE_KIND_STYLE[c.kind] ?? SCHEDULE_KIND_STYLE.other,
                        )}
                      >
                        {c.category}
                      </span>
                    ))}
                  </td>
                );
              })}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
