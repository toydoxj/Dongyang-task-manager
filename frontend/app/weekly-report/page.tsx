"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";

import { useAuth } from "@/components/AuthGuard";
import LoadingState from "@/components/ui/LoadingState";
import {
  downloadWeeklyReportPdf,
  fetchWeeklyReport,
  type WeeklyEmployeeWorkRow,
  type WeeklyPersonalScheduleEntry,
  type WeeklyReport,
  type WeeklyReportRange,
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

function addDays(d: Date, n: number): Date {
  const r = new Date(d);
  r.setDate(r.getDate() + n);
  return r;
}

/** 사용자 default: 오늘이 수요일(weekday=3)이거나 그 이후(목/금/토/일)이면
 * 다음주 월요일을, 그 외(월/화)는 이번주 월요일을 시작일로 한다. */
function defaultWeekStart(today: Date = new Date()): Date {
  const wd = today.getDay(); // 0=일, 1=월, ..., 6=토
  const thisMon = mondayOf(today);
  // wd in {3,4,5,6,0}이면 다음 월요일. wd in {1,2}이면 이번 월요일.
  const isWedOrLater = wd >= 3 || wd === 0;
  return isWedOrLater ? addDays(thisMon, 7) : thisMon;
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
  // 3개 날짜 state — 사용자 default 계산.
  const [weekStart, setWeekStart] = useState<string>(() =>
    toIsoDate(defaultWeekStart()),
  );
  const [weekEnd, setWeekEnd] = useState<string>(() =>
    toIsoDate(addDays(defaultWeekStart(), 4)),
  );
  const [lastWeekStart, setLastWeekStart] = useState<string>(() =>
    toIsoDate(addDays(defaultWeekStart(), -7)),
  );
  const [downloading, setDownloading] = useState(false);

  const range: WeeklyReportRange = {
    weekStart,
    weekEnd: weekEnd || undefined,
    lastWeekStart: lastWeekStart || undefined,
  };

  const { data, error, isLoading } = useSWR(
    user && weekStart ? ["weekly-report", weekStart, weekEnd, lastWeekStart] : null,
    () => fetchWeeklyReport(range),
  );

  /** 이번주 시작일 변경 → 종료일/지난주 시작일 자동 동기화. 사용자가 그 후
   * 종료일/지난주 시작일을 직접 수정하면 그 값 유지. */
  const handleWeekStartChange = (value: string): void => {
    if (!value) return;
    const d = new Date(`${value}T00:00:00`);
    if (Number.isNaN(d.getTime())) return;
    const newStart = mondayOf(d);
    setWeekStart(toIsoDate(newStart));
    setWeekEnd(toIsoDate(addDays(newStart, 4)));
    setLastWeekStart(toIsoDate(addDays(newStart, -7)));
  };

  const handleDownload = async (): Promise<void> => {
    setDownloading(true);
    try {
      await downloadWeeklyReportPdf(range);
    } catch (e) {
      alert(e instanceof Error ? e.message : "PDF 다운로드 실패");
    } finally {
      setDownloading(false);
    }
  };

  const teamWorkNames = useMemo<string[]>(
    () => (data ? Object.keys(data.team_work).sort(teamSort) : []),
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
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col text-xs text-zinc-500">
            지난주 시작일
            <input
              type="date"
              value={lastWeekStart}
              onChange={(e) => setLastWeekStart(e.target.value)}
              className="mt-1 rounded border border-zinc-300 bg-white px-2 py-1 text-sm dark:border-zinc-700 dark:bg-zinc-900"
            />
          </label>
          <label className="flex flex-col text-xs text-zinc-500">
            이번주 시작일 <span className="text-zinc-400">(월요일)</span>
            <input
              type="date"
              value={weekStart}
              onChange={(e) => handleWeekStartChange(e.target.value)}
              className="mt-1 rounded border border-zinc-300 bg-white px-2 py-1 text-sm dark:border-zinc-700 dark:bg-zinc-900"
            />
          </label>
          <label className="flex flex-col text-xs text-zinc-500">
            이번주 종료일
            <input
              type="date"
              value={weekEnd}
              onChange={(e) => setWeekEnd(e.target.value)}
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
          teamWorkNames={teamWorkNames}
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
  teamWorkNames: string[];
  scheduleMatrix: Record<string, Record<string, WeeklyPersonalScheduleEntry[][]>>;
  scheduleTeams: string[];
}

function ReportPreview({
  data,
  weekStart,
  teamWorkNames,
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

      {/* 팀별 업무 현황 — 직원 × 프로젝트 행 단위 */}
      <Section title="■ 팀별 업무 현황">
        {teamWorkNames.length === 0 ? (
          <p className="text-xs text-zinc-500">(배정된 진행 프로젝트 없음)</p>
        ) : (
          <div className="space-y-3">
            {teamWorkNames.map((team) => (
              <TeamWorkTable
                key={team}
                team={team}
                rows={data.team_work[team]}
              />
            ))}
          </div>
        )}
      </Section>
    </div>
  );
}

/** 같은 직원의 첫 row만 이름/직책 표시 (rowspan 효과). */
function TeamWorkTable({
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
              <th className="border-b border-r border-zinc-200 px-2 py-1.5 text-left font-medium dark:border-zinc-800">
                이번주 업무
              </th>
              <th className="border-b border-zinc-200 px-2 py-1.5 text-left font-medium dark:border-zinc-800">
                비고
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
                    {row.project_name}
                  </td>
                  <td className="border-r border-zinc-200 px-2 py-1 align-top dark:border-zinc-800">
                    {row.client}
                  </td>
                  <td className="border-r border-zinc-200 px-2 py-1 align-top dark:border-zinc-800">
                    {row.stage}
                  </td>
                  <td className="border-r border-zinc-200 px-2 py-1 align-top text-zinc-600 dark:border-zinc-800 dark:text-zinc-400">
                    {row.last_week_summary || "—"}
                  </td>
                  <td className="border-r border-zinc-200 px-2 py-1 align-top dark:border-zinc-800">
                    {row.this_week_plan || "—"}
                  </td>
                  <td className="px-2 py-1 align-top text-zinc-500">
                    {row.note}
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
