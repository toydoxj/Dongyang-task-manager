"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";

import { useAuth } from "@/components/AuthGuard";
import LoadingState from "@/components/ui/LoadingState";
import {
  buildScheduleByEmployee,
  buildWeekDays,
} from "@/components/weekly-report/ScheduleMini";
import PublishChecklist from "@/components/weekly-report/PublishChecklist";
import ReportPreview from "@/components/weekly-report/ReportPreview";
import SectionNav from "@/components/weekly-report/SectionNav";
import StatusBar from "@/components/weekly-report/StatusBar";
import {
  downloadLastPublishedWeeklyReportPdf,
  downloadWeeklyReportPdf,
  fetchLastPublishedWeeklyReport,
  fetchWeeklyReport,
  publishWeeklyReport,
  type WeeklyHoliday,
  type WeeklyReportRange,
} from "@/lib/api";

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
  const [downloadingLast, setDownloadingLast] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [publishOpen, setPublishOpen] = useState(false);
  // 새로고침 카운터 — 증가 시 SWR 키 변경 + force_refresh=true로 fetch (PR-AD)
  const [refreshTick, setRefreshTick] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  // 사용자가 lastWeekStart를 한 번이라도 직접 수정했으면 last-published 자동 셋팅 차단
  const [lastWeekStartAuto, setLastWeekStartAuto] = useState(true);
  // 마지막 발행 정보 — admin "[최근 발행 PDF]" 버튼 활성/툴팁용
  const [lastPublishedInfo, setLastPublishedInfo] = useState<{
    weekStart: string;
    weekEnd: string;
    publishedAt: string | null;
  } | null>(null);

  const range: WeeklyReportRange = {
    weekStart,
    weekEnd: weekEnd || undefined,
    lastWeekStart: lastWeekStart || undefined,
  };

  // 마지막 발행 로그 기반 자동 lastWeekStart 셋팅 + 최근 발행 정보 보관 (mount 1회).
  // 발행된 일지의 week_end + 1일 = 다음 일지의 last_week_start (저번주 시작 기준).
  useEffect(() => {
    if (!user) return;
    void fetchLastPublishedWeeklyReport()
      .then((info) => {
        if (!info.week_end || !info.week_start) return;
        setLastPublishedInfo({
          weekStart: info.week_start,
          weekEnd: info.week_end,
          publishedAt: info.published_at ?? null,
        });
        if (!lastWeekStartAuto) return;
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

  const { data, error, isLoading, mutate } = useSWR(
    user && weekStart
      ? ["weekly-report", weekStart, weekEnd, lastWeekStart, refreshTick]
      : null,
    () => fetchWeeklyReport(range, { forceRefresh: refreshTick > 0 }),
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

  const handleRefresh = async (): Promise<void> => {
    setRefreshing(true);
    try {
      // refreshTick 증가 → SWR key 변경 → force_refresh=true로 새 fetch
      setRefreshTick((t) => t + 1);
      // mutate로 다음 tick에 fetch 보장 (key 변경만으로도 트리거되지만 명시).
      await mutate();
    } catch (e) {
      alert(e instanceof Error ? e.message : "새로고침 실패");
    } finally {
      setRefreshing(false);
    }
  };

  const handleDownloadLastPublished = async (): Promise<void> => {
    setDownloadingLast(true);
    try {
      await downloadLastPublishedWeeklyReportPdf();
    } catch (e) {
      alert(e instanceof Error ? e.message : "최근 발행 PDF 다운로드 실패");
    } finally {
      setDownloadingLast(false);
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
      // 발행 직후 [최근 발행 PDF] 버튼 즉시 활성화
      void fetchLastPublishedWeeklyReport()
        .then((info) => {
          if (info.week_start && info.week_end) {
            setLastPublishedInfo({
              weekStart: info.week_start,
              weekEnd: info.week_end,
              publishedAt: info.published_at ?? null,
            });
          }
        })
        .catch(() => {
          /* 무시 */
        });
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
            onClick={handleRefresh}
            disabled={refreshing || isLoading}
            className="rounded border border-zinc-300 bg-white px-3 py-1.5 text-sm font-medium text-zinc-700 hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800"
            title="cache 무시하고 최신 데이터로 다시 집계 (5분 TTL 적용 중)"
          >
            {refreshing || isLoading ? "갱신 중..." : "새로고침"}
          </button>
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
              onClick={handleDownloadLastPublished}
              disabled={downloadingLast || !lastPublishedInfo}
              className="rounded border border-emerald-600 bg-white px-3 py-1.5 text-sm font-medium text-emerald-700 hover:bg-emerald-50 disabled:opacity-50 dark:bg-zinc-900 dark:text-emerald-400 dark:hover:bg-emerald-950/40"
              title={
                lastPublishedInfo
                  ? `최근 발행본 (${lastPublishedInfo.weekStart} ~ ${lastPublishedInfo.weekEnd}${lastPublishedInfo.publishedAt ? ` · ${lastPublishedInfo.publishedAt.slice(0, 10)} 발행` : ""})`
                  : "발행 이력 없음"
              }
            >
              {downloadingLast ? "다운로드 중..." : "최근 발행 PDF"}
            </button>
          )}
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




