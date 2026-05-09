"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";

import { useAuth } from "@/components/AuthGuard";
import LoadingState from "@/components/ui/LoadingState";
import {
  downloadWeeklyReportPdf,
  fetchWeeklyReport,
  type WeeklyPersonalScheduleEntry,
  type WeeklyReport,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/** 주어진 날짜가 속한 주의 월요일 (KST 가정). */
function mondayOf(d: Date): Date {
  const date = new Date(d);
  const day = date.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  date.setDate(date.getDate() + diff);
  date.setHours(0, 0, 0, 0);
  return date;
}

function toIsoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

const TEAM_ORDER: Record<string, number> = {
  구조1팀: 1,
  구조2팀: 2,
  구조3팀: 3,
  구조4팀: 4,
  진단팀: 5,
};
const teamSort = (a: string, b: string): number =>
  (TEAM_ORDER[a] ?? 99) - (TEAM_ORDER[b] ?? 99);

const WEEKDAYS = ["월", "화", "수", "목", "금"] as const;

/** 카테고리 라벨 → tailwind classes (PDF 색상 라벨과 동일 맥락). */
const CATEGORY_STYLE: Record<string, string> = {
  외근: "bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300",
  동행: "bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300",
  출장: "bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-300",
  연차: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
  휴가: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
  반차: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300",
  파견: "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300",
  교육: "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300",
};

/** {team: {employee: [day0..day4 entries]}} 매트릭스. */
function buildScheduleMatrix(
  entries: WeeklyPersonalScheduleEntry[],
  weekStart: string,
): Record<string, Record<string, WeeklyPersonalScheduleEntry[][]>> {
  const start = new Date(`${weekStart}T00:00:00`);
  const result: Record<string, Record<string, WeeklyPersonalScheduleEntry[][]>> = {};
  for (const e of entries) {
    const sd = new Date(`${e.start_date}T00:00:00`);
    const ed = new Date(`${e.end_date}T00:00:00`);
    if (Number.isNaN(sd.getTime()) || Number.isNaN(ed.getTime())) continue;
    const team = e.team || "기타";
    const emp = e.employee_name;
    if (!result[team]) result[team] = {};
    if (!result[team][emp]) {
      result[team][emp] = WEEKDAYS.map(() => []);
    }
    for (let i = 0; i < 5; i++) {
      const day = new Date(start);
      day.setDate(start.getDate() + i);
      if (sd <= day && day <= ed) result[team][emp][i].push(e);
    }
  }
  return result;
}

export default function WeeklyReportPage() {
  const { user } = useAuth();
  const [weekStart, setWeekStart] = useState<string>(
    toIsoDate(mondayOf(new Date())),
  );
  const [downloading, setDownloading] = useState(false);

  const { data, error, isLoading } = useSWR(
    user && weekStart ? ["weekly-report", weekStart] : null,
    () => fetchWeeklyReport(weekStart),
  );

  const handleDateChange = (value: string): void => {
    if (!value) return;
    const d = new Date(`${value}T00:00:00`);
    if (Number.isNaN(d.getTime())) return;
    setWeekStart(toIsoDate(mondayOf(d)));
  };

  const handleDownload = async (): Promise<void> => {
    setDownloading(true);
    try {
      await downloadWeeklyReportPdf(weekStart);
    } catch (e) {
      alert(e instanceof Error ? e.message : "PDF 다운로드 실패");
    } finally {
      setDownloading(false);
    }
  };

  const teamNames = useMemo<string[]>(
    () => (data ? Object.keys(data.teams).sort(teamSort) : []),
    [data],
  );
  const scheduleMatrix = useMemo(
    () => (data ? buildScheduleMatrix(data.personal_schedule, weekStart) : {}),
    [data, weekStart],
  );
  const scheduleTeams = useMemo(
    () => Object.keys(scheduleMatrix).sort(teamSort),
    [scheduleMatrix],
  );

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">주간 업무일지</h1>
          <p className="mt-1 text-sm text-zinc-500">
            월~금 주차 단위 자동 집계 (KST). 데이터: 노션 미러 + employees + 공지.
          </p>
        </div>
        <div className="flex items-end gap-2">
          <label className="flex flex-col text-xs text-zinc-500">
            주차 시작 (월요일)
            <input
              type="date"
              value={weekStart}
              onChange={(e) => handleDateChange(e.target.value)}
              className="mt-1 rounded border border-zinc-300 bg-white px-2 py-1 text-sm dark:border-zinc-700 dark:bg-zinc-900"
            />
          </label>
          <button
            onClick={handleDownload}
            disabled={downloading || !data}
            className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {downloading ? "다운로드 중..." : "PDF 다운로드"}
          </button>
        </div>
      </header>

      {isLoading && <LoadingState />}
      {error && (
        <div className="rounded-md border border-red-500/40 bg-red-500/5 p-4 text-sm text-red-600 dark:text-red-400">
          {error instanceof Error ? error.message : String(error)}
        </div>
      )}

      {data && (
        <ReportPreview
          data={data}
          weekStart={weekStart}
          teamNames={teamNames}
          scheduleMatrix={scheduleMatrix}
          scheduleTeams={scheduleTeams}
        />
      )}
    </div>
  );
}

interface PreviewProps {
  data: WeeklyReport;
  weekStart: string;
  teamNames: string[];
  scheduleMatrix: Record<string, Record<string, WeeklyPersonalScheduleEntry[][]>>;
  scheduleTeams: string[];
}

function ReportPreview({
  data,
  weekStart,
  teamNames,
  scheduleMatrix,
  scheduleTeams,
}: PreviewProps) {
  const period = `${data.period_start} ~ ${data.period_end}`;
  return (
    <div className="space-y-4">
      {/* 인원 */}
      <Section title="■ 인원현황">
        <div className="rounded border border-zinc-200 bg-zinc-50 p-2 text-sm dark:border-zinc-800 dark:bg-zinc-900">
          <span className="font-medium">{period}</span>
          <span className="mx-2 text-zinc-400">│</span>
          총원 <strong>{data.headcount.total}</strong>인
          {Object.entries(data.headcount.by_occupation).map(([k, v]) => (
            <span key={k} className="text-zinc-600 dark:text-zinc-400">
              {" "}
              · {k} {v}
            </span>
          ))}
          {(data.headcount.new_this_week > 0 ||
            data.headcount.resigned_this_week.length > 0) && (
            <>
              <span className="mx-2 text-zinc-400">│</span>
              <span className="rounded bg-zinc-200 px-1.5 py-0.5 text-xs dark:bg-zinc-700">
                변동
              </span>{" "}
              신규 {data.headcount.new_this_week}
              {data.headcount.resigned_this_week.length > 0 && (
                <span className="text-red-600 dark:text-red-400">
                  {" "}
                  / 퇴사 {data.headcount.resigned_this_week.length} (
                  {data.headcount.resigned_this_week.join(", ")})
                </span>
              )}
            </>
          )}
        </div>
      </Section>

      {/* 공지 / 교육 (있을 때만) */}
      {(data.notices.length > 0 || data.education.length > 0) && (
        <div className="grid gap-3 md:grid-cols-2">
          {data.notices.length > 0 && (
            <Section title="■ 주요 공지사항">
              <BulletList items={data.notices} />
            </Section>
          )}
          {data.education.length > 0 && (
            <Section title="■ 교육 일정">
              <BulletList items={data.education} />
            </Section>
          )}
        </div>
      )}

      {/* 날인대장 */}
      <Section title="■ 날인대장">
        <SimpleTable
          cols={["프로젝트명", "발주처", "유형", "상태", "처리자", "제출예정일"]}
          rows={data.seal_log.map((s) => [
            s.project_name,
            s.client,
            s.seal_type,
            s.status,
            s.handler,
            s.due_date ?? "",
          ])}
          empty="(날인 진행건 없음)"
        />
      </Section>

      {/* 영업 */}
      <Section title="■ 영업">
        <SimpleTable
          cols={[
            "영업번호",
            "내용",
            "PROJECT",
            "발주처",
            "규모",
            "견적가",
            "단계",
            "제출일",
          ]}
          rows={data.sales.map((s) => [
            s.code,
            s.category.join("/"),
            s.is_bid ? `${s.name}  [입찰]` : s.name,
            s.client,
            s.scale,
            s.estimated_amount
              ? `₩${s.estimated_amount.toLocaleString()}`
              : "",
            s.stage,
            s.submission_date ?? "",
          ])}
          empty="(이번 주 영업건 없음)"
        />
      </Section>

      {/* 완료 / 신규 */}
      <div className="grid gap-3 md:grid-cols-2">
        <Section title="■ 이번 주 완료">
          <SimpleTable
            cols={["CODE", "프로젝트명", "팀"]}
            rows={data.completed.map((c) => [
              c.code,
              c.name,
              c.teams.join(", "),
            ])}
            empty="(완료 없음)"
          />
        </Section>
        <Section title="■ 이번 주 신규">
          <SimpleTable
            cols={["CODE", "프로젝트명", "단계", "팀"]}
            rows={data.new_projects.map((n) => [
              n.code,
              n.name,
              n.stage,
              n.teams.join(", "),
            ])}
            empty="(신규 없음 — 휴리스틱 기반)"
          />
        </Section>
      </div>

      {/* 개인 주간 일정 매트릭스 */}
      <Section title="■ 개인 주간 일정">
        {scheduleTeams.length === 0 ? (
          <p className="text-xs text-zinc-500">
            (이번 주 등록된 외근/연차/파견 일정 없음)
          </p>
        ) : (
          <div className="space-y-3">
            {scheduleTeams.map((team) => (
              <div key={team}>
                <h3 className="mb-1 text-sm font-semibold">{team}</h3>
                <div className="overflow-x-auto rounded border border-zinc-200 dark:border-zinc-800">
                  <table className="w-full border-collapse text-xs">
                    <thead className="bg-zinc-100 dark:bg-zinc-900">
                      <tr>
                        <th className="border-b border-zinc-200 px-2 py-1 text-left font-medium dark:border-zinc-800">
                          담당자
                        </th>
                        {WEEKDAYS.map((d) => (
                          <th
                            key={d}
                            className="w-12 border-b border-zinc-200 px-1 py-1 text-center font-medium dark:border-zinc-800"
                          >
                            {d}
                          </th>
                        ))}
                        <th className="border-b border-zinc-200 px-2 py-1 text-left font-medium dark:border-zinc-800">
                          비고
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(scheduleMatrix[team]).map(
                        ([emp, days]) => {
                          const projectCodes = Array.from(
                            new Set(
                              days.flatMap((cells) =>
                                cells
                                  .map((c) => c.project_code)
                                  .filter(Boolean),
                              ),
                            ),
                          );
                          return (
                            <tr
                              key={emp}
                              className="border-b border-zinc-100 last:border-0 dark:border-zinc-800"
                            >
                              <td className="px-2 py-1">{emp}</td>
                              {days.map((cells, i) => (
                                <td
                                  key={i}
                                  className="px-1 py-1 text-center"
                                >
                                  {cells.map((c, j) => (
                                    <span
                                      key={j}
                                      className={cn(
                                        "mr-0.5 inline-block rounded px-1 py-0.5 text-[10px] font-medium",
                                        CATEGORY_STYLE[c.category] ??
                                          "bg-zinc-200 text-zinc-700 dark:bg-zinc-700 dark:text-zinc-200",
                                      )}
                                    >
                                      {c.category.slice(0, 2)}
                                    </span>
                                  ))}
                                </td>
                              ))}
                              <td className="px-2 py-1 text-zinc-600 dark:text-zinc-400">
                                {projectCodes.join(", ")}
                              </td>
                            </tr>
                          );
                        },
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
          </div>
        )}
      </Section>

      {/* 팀별 진행 프로젝트 */}
      <Section title="■ 팀별 진행 프로젝트">
        {teamNames.length === 0 ? (
          <p className="text-xs text-zinc-500">(팀 배정된 진행 프로젝트 없음)</p>
        ) : (
          <div className="space-y-3">
            {teamNames.map((team) => (
              <div key={team}>
                <h3 className="mb-1 text-sm font-semibold">
                  {team}{" "}
                  <span className="text-xs font-normal text-zinc-500">
                    ({data.teams[team].length}건)
                  </span>
                </h3>
                <SimpleTable
                  cols={[
                    "CODE",
                    "프로젝트명",
                    "발주처",
                    "PM",
                    "단계",
                    "진행률",
                    "마감",
                    "담당자 / 금주예정",
                  ]}
                  rows={data.teams[team].map((r) => [
                    r.code,
                    r.name,
                    r.client,
                    r.pm,
                    r.stage,
                    `${Math.round(r.progress * 100)}%`,
                    r.end_date ?? "",
                    r.weekly_plan
                      ? `${r.assignees.join(", ")} — ${r.weekly_plan}`
                      : r.assignees.join(", "),
                  ])}
                />
              </div>
            ))}
          </div>
        )}
      </Section>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-2">
      <h2 className="border-l-2 border-emerald-500 bg-emerald-50/60 px-2 py-1 text-sm font-semibold text-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-300">
        {title}
      </h2>
      {children}
    </section>
  );
}

function BulletList({ items }: { items: string[] }) {
  return (
    <ul className="list-inside list-disc space-y-0.5 text-sm">
      {items.map((s, i) => (
        <li key={i}>{s}</li>
      ))}
    </ul>
  );
}

function SimpleTable({
  cols,
  rows,
  empty,
}: {
  cols: string[];
  rows: (string | number)[][];
  empty?: string;
}) {
  if (rows.length === 0 && empty) {
    return (
      <div className="rounded border border-dashed border-zinc-300 px-3 py-2 text-center text-xs italic text-zinc-400 dark:border-zinc-700">
        {empty}
      </div>
    );
  }
  return (
    <div className="overflow-x-auto rounded border border-zinc-200 dark:border-zinc-800">
      <table className="w-full border-collapse text-xs">
        <thead className="bg-zinc-100 dark:bg-zinc-900">
          <tr>
            {cols.map((c) => (
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
          {rows.map((row, i) => (
            <tr
              key={i}
              className="border-b border-zinc-100 last:border-0 dark:border-zinc-800"
            >
              {row.map((cell, j) => (
                <td key={j} className="px-2 py-1 align-top">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
