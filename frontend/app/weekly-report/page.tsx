"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";

import { useAuth } from "@/components/AuthGuard";
import LoadingState from "@/components/ui/LoadingState";
import PublishChecklist from "@/components/weekly-report/PublishChecklist";
import SectionNav from "@/components/weekly-report/SectionNav";
import StatusBar from "@/components/weekly-report/StatusBar";
import {
  downloadLastPublishedWeeklyReportPdf,
  downloadWeeklyReportPdf,
  fetchLastPublishedWeeklyReport,
  fetchWeeklyReport,
  publishWeeklyReport,
  type WeeklyEmployeeWorkRow,
  type WeeklyHoliday,
  type WeeklyPersonalScheduleEntry,
  type WeeklyReport,
  type WeeklyReportRange,
  type WeeklyStageProject,
  type WeeklyTeamMember,
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
  본부: 6,
};
const teamSort = (a: string, b: string): number =>
  (TEAM_ORDER[a] ?? 99) - (TEAM_ORDER[b] ?? 99);

/** 개인일정 grid에서 5팀 column 표시 순서 (본부는 5번째 column 끝에 별도 stack). */
const SCHEDULE_GRID_TEAMS = ["구조1팀", "구조2팀", "구조3팀", "구조4팀", "진단팀"] as const;
const SCHEDULE_EXTRA_TEAM = "본부";

/** 개인일정 cell 색상 — task source 기준 (사용자 결정 2026-05-09):
 * project=파랑, sale=초록, other=회색 (개인 휴가/연차 등). */
/** 프로젝트 상세 link — admin만 활성화. 비admin은 plain text (사용자 결정 2026-05-11). */
function ProjectLink({ id, children }: { id: string; children: React.ReactNode }) {
  const { user } = useAuth();
  if (!id || user?.role !== "admin") return <>{children}</>;
  return (
    <Link
      href={`/projects/${encodeURIComponent(id)}`}
      className="text-blue-700 underline-offset-2 hover:underline dark:text-blue-400"
    >
      {children}
    </Link>
  );
}

/** 영업 상세 link — admin만 활성화. 비admin은 plain text. */
function SaleLink({ id, children }: { id: string; children: React.ReactNode }) {
  const { user } = useAuth();
  if (!id || user?.role !== "admin") return <>{children}</>;
  return (
    <Link
      href={`/sales?sale=${encodeURIComponent(id)}&from=${encodeURIComponent("/weekly-report")}`}
      className="text-emerald-700 underline-offset-2 hover:underline dark:text-emerald-400"
    >
      {children}
    </Link>
  );
}

const SCHEDULE_KIND_STYLE: Record<string, string> = {
  project: "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300",
  sale: "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300",
  other: "bg-zinc-200 text-zinc-700 dark:bg-zinc-700 dark:text-zinc-200",
};

/** 직원 단위 일정 lookup: {employee_name: [day0..day4 entries]}. team 무관 — team_members로 분류. */
function buildScheduleByEmployee(
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
function buildWeekDays(weekStart: string, weekEnd: string): { iso: string; label: string }[] {
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
  const [publishing, setPublishing] = useState(false);
  const [publishOpen, setPublishOpen] = useState(false);
  // 사용자가 lastWeekStart를 한 번이라도 직접 수정했으면 last-published 자동 셋팅 차단
  const [lastWeekStartAuto, setLastWeekStartAuto] = useState(true);

  const range: WeeklyReportRange = {
    weekStart,
    weekEnd: weekEnd || undefined,
    lastWeekStart: lastWeekStart || undefined,
  };

  // 마지막 발행 로그 기반 자동 lastWeekStart 셋팅 (mount 1회).
  // 발행된 일지의 week_end + 1일 = 다음 일지의 last_week_start (저번주 시작 기준).
  useEffect(() => {
    if (!user || !lastWeekStartAuto) return;
    void fetchLastPublishedWeeklyReport()
      .then((info) => {
        if (!info.week_end) return;
        const nextLws = new Date(`${info.week_end}T00:00:00`);
        nextLws.setDate(nextLws.getDate() + 1);
        setLastWeekStart(toIsoDate(nextLws));
      })
      .catch(() => {
        /* 발행 이력 없거나 실패 — 무시 */
      });
    // user/auto flag만 의존성. lastWeekStart 자체는 사용자 수정 차단 위해 제외.
     
  }, [user, lastWeekStartAuto]);

  const isAdmin = user?.role === "admin";

  const { data, error, isLoading } = useSWR(
    user && weekStart ? ["weekly-report", weekStart, weekEnd, lastWeekStart] : null,
    () => fetchWeeklyReport(range),
  );

  /** 이번주 시작일 변경 → 종료일/지난주 시작일 자동 동기화. 사용자가 그 후
   * 종료일/지난주 시작일을 직접 수정하면 그 값 유지 (자동 셋팅 차단). */
  const handleWeekStartChange = (value: string): void => {
    if (!value) return;
    const d = new Date(`${value}T00:00:00`);
    if (Number.isNaN(d.getTime())) return;
    const newStart = mondayOf(d);
    setWeekStart(toIsoDate(newStart));
    setWeekEnd(toIsoDate(addDays(newStart, 4)));
    setLastWeekStart(toIsoDate(addDays(newStart, -7)));
    setLastWeekStartAuto(false); // week_start 변경하면 last-published 자동 셋팅 차단
  };

  const handleDownload = async (): Promise<void> => {
    setDownloading(true);
    try {
      if (isAdmin) {
        // admin: 현재 입력된 기간 기준으로 PDF 미리 확인
        await downloadWeeklyReportPdf(range);
      } else {
        // 일반 직원: 최근 발행된 PDF만 다운로드
        await downloadLastPublishedWeeklyReportPdf();
      }
    } catch (e) {
      alert(e instanceof Error ? e.message : "PDF 처리 실패");
    } finally {
      setDownloading(false);
    }
  };

  const openPublishChecklist = (): void => {
    if (!data) return;
    setPublishOpen(true);
  };

  const doPublish = async (): Promise<void> => {
    setPublishing(true);
    try {
      const res = await publishWeeklyReport(range);
      const failNote = res.notify_failed_count
        ? ` (실패 ${res.notify_failed_count})`
        : "";
      alert(
        `발행 완료\n파일: ${res.file_name}\n전송 ${res.recipient_count}명${failNote}`,
      );
      setPublishOpen(false);
    } catch (e) {
      alert(e instanceof Error ? e.message : "발행 실패");
    } finally {
      setPublishing(false);
    }
  };

  const teamWorkNames = useMemo<string[]>(
    () => (data ? Object.keys(data.team_work).sort(teamSort) : []),
    [data],
  );
  const scheduleByEmployee = useMemo(
    () =>
      data
        ? buildScheduleByEmployee(data.personal_schedule, weekStart, weekEnd)
        : {},
    [data, weekStart, weekEnd],
  );
  const weekDays = useMemo(
    () => buildWeekDays(weekStart, weekEnd),
    [weekStart, weekEnd],
  );
  const holidayByIso = useMemo<Record<string, WeeklyHoliday[]>>(() => {
    if (!data) return {};
    const map: Record<string, WeeklyHoliday[]> = {};
    for (const h of data.holidays) {
      if (!map[h.date]) map[h.date] = [];
      map[h.date].push(h);
    }
    return map;
  }, [data]);

  return (
    <div className="space-y-4">
      <header
        id="publish-controls"
        className="flex flex-wrap items-end justify-between gap-3"
      >
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
              onChange={(e) => {
                setLastWeekStart(e.target.value);
                setLastWeekStartAuto(false);
              }}
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
            disabled={downloading || (isAdmin && !data)}
            className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
            title={
              isAdmin
                ? "현재 기간으로 PDF 미리보기 (다운로드)"
                : "최근 발행된 주간업무일지 PDF 다운로드"
            }
          >
            {downloading
              ? isAdmin
                ? "확인 중..."
                : "다운로드 중..."
              : isAdmin
                ? "PDF 확인"
                : "PDF 다운로드"}
          </button>
          {isAdmin && (
            <button
              onClick={openPublishChecklist}
              disabled={publishing || !data}
              className="rounded bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
              title="WORKS Drive 업로드 + 전직원 알림 발송"
            >
              {publishing ? "발행 중..." : "발행"}
            </button>
          )}
        </div>
      </header>

      {isLoading && <LoadingState />}
      {error && (
        <div className="rounded-md border border-red-500/40 bg-red-500/5 p-4 text-sm text-red-600 dark:text-red-400">
          {error instanceof Error ? error.message : String(error)}
        </div>
      )}

      <StatusBar data={data ?? null} isAdmin={isAdmin} />
      <SectionNav />

      {data && (
        <ReportPreview
          data={data}
          teamWorkNames={teamWorkNames}
          scheduleByEmployee={scheduleByEmployee}
          weekDays={weekDays}
          holidayByIso={holidayByIso}
        />
      )}

      {publishOpen && data && isAdmin && (
        <PublishChecklist
          data={data}
          publishing={publishing}
          onConfirm={doPublish}
          onClose={() => setPublishOpen(false)}
        />
      )}
    </div>
  );
}

interface PreviewProps {
  data: WeeklyReport;
  teamWorkNames: string[];
  scheduleByEmployee: Record<string, WeeklyPersonalScheduleEntry[][]>;
  weekDays: { iso: string; label: string }[];
  holidayByIso: Record<string, WeeklyHoliday[]>;
}

function ReportPreview({
  data,
  teamWorkNames,
  scheduleByEmployee,
  weekDays,
  holidayByIso,
}: PreviewProps) {
  const period = `${data.period_start} ~ ${data.period_end}`;
  return (
    <div className="weekly-report-tables space-y-4">
      {/* PDF 헤더 양식 동등 — 좌측 제목/기간, 우측 회사명 */}
      <div className="flex items-end justify-between gap-3 border-b-2 border-emerald-600/70 pb-1">
        <div className="text-lg font-bold tracking-wide">
          주간업무일지
          <span className="ml-2 text-sm font-medium text-zinc-500">{period}</span>
        </div>
        <div className="text-right leading-tight">
          <div className="text-sm font-bold text-zinc-700 dark:text-zinc-200">
            (주)동양구조
          </div>
          <div className="text-[9px] font-bold tracking-tighter text-zinc-500">
            Dongyang Consulting Engineers. Co., Ltd.
          </div>
        </div>
      </div>

      {/* 인원 — PDF와 동일: 구조설계/안전진단/관리 순서 + 총원 = 3개 합계 (기타 제외).
          구조설계 = 노션 '구조설계' + 1, 관리 = 노션 '관리세무' + 1. */}
      <Section title="인원현황" id="headcount" badge="auto" sourceHref="/admin/employees">
        {(() => {
          const sDesign = (data.headcount.by_occupation["구조설계"] ?? 0) + 1;
          const sInspect = data.headcount.by_occupation["안전진단"] ?? 0;
          const sOffice = (data.headcount.by_occupation["관리세무"] ?? 0) + 1;
          const totalDisplay = sDesign + sInspect + sOffice;
          return (
        <div className="rounded border border-zinc-200 bg-zinc-50 p-2 text-sm dark:border-zinc-800 dark:bg-zinc-900">
          총원 <strong>{totalDisplay}</strong>인
          <span className="text-zinc-600 dark:text-zinc-400">
            <span className="mx-1 text-zinc-400">│</span>구조설계 {sDesign}
          </span>
          <span className="text-zinc-600 dark:text-zinc-400">
            <span className="mx-1 text-zinc-400">│</span>안전진단 {sInspect}
          </span>
          <span className="text-zinc-600 dark:text-zinc-400">
            <span className="mx-1 text-zinc-400">│</span>관리 {sOffice}
          </span>
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
          {data.holidays.length > 0 && (
            <>
              <span className="mx-2 text-zinc-400">│</span>
              <span className="rounded bg-zinc-200 px-1.5 py-0.5 text-xs dark:bg-zinc-700">
                공휴일
              </span>{" "}
              {data.holidays
                .map(
                  (h) =>
                    `${h.date.slice(5).replace("-", "/")} ${h.name}${
                      h.source === "company" ? "(사내)" : ""
                    }`,
                )
                .join(" · ")}
            </>
          )}
        </div>
          );
        })()}
      </Section>

      {/* [공지][교육][건의] 3-col grid (모두 있어야 보임 — 빈 칸은 "(없음)" 표시) */}
      <div id="manual-section" className="grid gap-3 md:grid-cols-3">
        <Section title="주요 공지사항" badge="manual" sourceHref="/admin/notices">
          {data.notices.length > 0 ? (
            <BulletList items={data.notices} />
          ) : (
            <p className="text-xs text-zinc-500">(없음)</p>
          )}
        </Section>
        <Section title="교육 일정" badge="manual" sourceHref="/admin/notices">
          {data.education.length > 0 ? (
            <BulletList items={data.education} />
          ) : (
            <p className="text-xs text-zinc-500">(없음)</p>
          )}
        </Section>
        <Section title="건의사항" badge="manual" sourceHref="/suggestions">
          {data.suggestions.length > 0 ? (
            <ul className="list-inside list-disc space-y-0.5 text-sm">
              {data.suggestions.map((s, i) => (
                <li key={i}>
                  {s.title}
                  <span className="ml-1 text-[10px] text-zinc-500">
                    · {s.author} · {s.status}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-zinc-500">(없음)</p>
          )}
        </Section>
      </div>

      {/* 완료 → 날인대장 세로 배치 (PDF와 동일) */}
      <Section title="완료 프로젝트" id="completed" badge="auto" sourceHref="/projects">
        <SimpleTable
          cols={["상태", "CODE", "프로젝트명", "발주처", "담당팀", "소요기간(개월)"]}
          rows={data.completed.map((c) => [
            c.status_label,
            c.code,
            <ProjectLink key="n" id={c.page_id}>{c.name}</ProjectLink>,
            c.client,
            c.teams.join(", "),
            c.duration_months != null ? c.duration_months.toFixed(1) : "",
          ])}
          empty="(완료 없음)"
        />
      </Section>
      <Section title="날인대장" id="seal-ledger" badge="auto" sourceHref="/seal-requests">
        <SimpleTable
          cols={["승인일", "CODE", "용역명", "제출처", "유형", "담당자"]}
          rows={data.seal_log.map((s) => [
            (s.approved_at ?? "").slice(5, 10).replace("-", "/"),
            s.code,
            <ProjectLink key="n" id={s.project_id}>{s.name}</ProjectLink>,
            s.submission_target,
            s.seal_type,
            s.requester,
          ])}
          empty="(저번주 승인된 날인 없음)"
        />
      </Section>

      {/* 영업 — PDF와 동일: 영업번호/PROJECT/발주처/규모/견적가/수주확률/비고 */}
      <Section title="영업" id="sales" badge="auto" sourceHref="/sales">
        <SimpleTable
          cols={[
            "영업번호",
            "PROJECT",
            "발주처",
            "규모",
            "견적가",
            "수주확률",
            "비고",
          ]}
          rows={data.sales.map((s) => [
            s.code,
            <SaleLink key="n" id={s.page_id}>{s.name}</SaleLink>,
            s.client,
            s.scale,
            s.estimated_amount
              ? `₩${s.estimated_amount.toLocaleString()}`
              : "",
            s.probability != null ? `${Math.round(s.probability)}%` : "",
            s.is_bid ? "(입찰)" : "",
          ])}
          empty="(저번주 시작 영업건 없음 — 노션 '영업시작일' 입력 필요)"
        />
      </Section>

      {/* 신규 프로젝트 (완료는 위 2-col에 배치됨) */}
      <Section title="신규 프로젝트" id="new-projects" badge="auto" sourceHref="/projects">
        <SimpleTable
          cols={["업무내용", "CODE", "용역명", "발주처", "규모", "용역비"]}
          rows={data.new_projects.map((n) => [
            n.work_types.join("/"),
            n.code,
            <ProjectLink key="n" id={n.page_id}>{n.name}</ProjectLink>,
            n.client,
            n.scale,
            n.contract_amount ? `₩${n.contract_amount.toLocaleString()}` : "",
          ])}
          empty="(신규 없음)"
        />
      </Section>

      {/* 개인 주간 일정 — 5팀 horizontal grid (본부는 진단팀 column 끝에 stack) */}
      <Section title="개인 주간 일정" id="personal-schedule" badge="auto" sourceHref="/schedule">
        <div className="grid gap-2 lg:grid-cols-5">
          {SCHEDULE_GRID_TEAMS.map((team) => (
            <ScheduleTeamCard
              key={team}
              team={team}
              members={data.team_members[team] ?? []}
              scheduleByEmployee={scheduleByEmployee}
              weekDays={weekDays}
              holidayByIso={holidayByIso}
              extra={
                team === "진단팀"
                  ? {
                      title: SCHEDULE_EXTRA_TEAM,
                      members: data.team_members[SCHEDULE_EXTRA_TEAM] ?? [],
                    }
                  : undefined
              }
            />
          ))}
        </div>
        {data.holidays.length > 0 && (
          <p className="text-[10px] text-zinc-500">
            ※ 공휴일:{" "}
            {data.holidays
              .map(
                (h) =>
                  `${h.date.slice(5)} ${h.name}${
                    h.source === "company" ? "(사내)" : ""
                  }`,
              )
              .join(" · ")}
          </p>
        )}
      </Section>

      {/* 팀별 업무 현황 — 직원 × 프로젝트 행 단위 */}
      <Section title="팀별 업무 현황" id="team-work" badge="auto" sourceHref="/admin/employee-work">
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

      {/* 대기 프로젝트 — 자체 2-열 분할 (대기가 길어 보류와 같이 두면 비대칭) */}
      <Section title="대기 프로젝트" id="waiting" badge="auto" sourceHref="/projects">
        <SplitStageGrid rows={data.waiting_projects} highlightStalled />
      </Section>

      {/* 보류 프로젝트 — 자체 2-열 분할 */}
      <Section title="보류 프로젝트" id="on-hold" badge="auto" sourceHref="/projects">
        <SplitStageGrid rows={data.on_hold_projects} />
      </Section>
    </div>
  );
}

/** 대기/보류 프로젝트를 절반씩 자체 2-col grid로 분할. */
function SplitStageGrid({
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
function StageProjectsTable({
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

interface ScheduleTeamCardProps {
  team: string;
  members: WeeklyTeamMember[];
  scheduleByEmployee: Record<string, WeeklyPersonalScheduleEntry[][]>;
  weekDays: { iso: string; label: string }[];
  holidayByIso: Record<string, WeeklyHoliday[]>;
  /** 진단팀 column에만 — 본부 직원을 같은 카드 아래에 stack 표시. */
  extra?: { title: string; members: WeeklyTeamMember[] };
}

function ScheduleTeamCard({
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

function ScheduleMiniTable({
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

function Section({
  title,
  id,
  badge,
  sourceHref,
  children,
}: {
  title: string;
  id?: string;
  badge?: SectionBadge;
  /** WEEK-005 — admin이 이 섹션의 원본/관리 페이지로 점프할 link. admin만 노출. */
  sourceHref?: string;
  children: React.ReactNode;
}) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  // PDF 양식과 동일 — 회색 배경 + 좌측 회색 막대, 불릿 마크 없음.
  return (
    <section id={id} className="scroll-mt-16 space-y-2">
      <h2 className="flex items-center gap-1.5 border-l-[3px] border-zinc-500 bg-zinc-200/70 px-2 py-1 text-xs font-bold text-zinc-700 dark:border-zinc-500 dark:bg-zinc-800/70 dark:text-zinc-200">
        <span>{title}</span>
        {badge && <BadgeChip kind={badge} />}
        {sourceHref && isAdmin && (
          <Link
            href={sourceHref}
            className="ml-auto inline-flex items-center gap-1 rounded border border-zinc-400 bg-white px-1.5 py-0.5 text-[10px] font-medium text-zinc-600 hover:bg-zinc-100 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
            title="원본/관리 페이지"
          >
            관리 ↗
          </Link>
        )}
      </h2>
      {children}
    </section>
  );
}

type SectionBadge = "auto" | "manual" | "review";

const BADGE_STYLE: Record<SectionBadge, string> = {
  auto: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  manual: "bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300",
  review: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
};
const BADGE_LABEL: Record<SectionBadge, string> = {
  auto: "자동 집계",
  manual: "수동 입력",
  review: "검토 필요",
};

function BadgeChip({ kind }: { kind: SectionBadge }) {
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-[9px] font-medium leading-none ${BADGE_STYLE[kind]}`}
    >
      {BADGE_LABEL[kind]}
    </span>
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

type CellValue = string | number | React.ReactNode;

function SimpleTable({
  cols,
  rows,
  empty,
}: {
  cols: string[];
  rows: CellValue[][];
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
                  {cell as React.ReactNode}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
