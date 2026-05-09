"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";

import { useAuth } from "@/components/AuthGuard";
import LoadingState from "@/components/ui/LoadingState";
import {
  downloadWeeklyReportPdf,
  fetchWeeklyReport,
  type WeeklyReport,
} from "@/lib/api";

/** 주어진 날짜가 속한 주의 월요일 (KST 가정). */
function mondayOf(d: Date): Date {
  const date = new Date(d);
  const day = date.getDay();
  const diff = day === 0 ? -6 : 1 - day; // 일요일이면 6일 전, 그 외엔 (1-day)일 전
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

function formatPeriod(report: WeeklyReport): string {
  return `${report.period_start} ~ ${report.period_end}`;
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

  // date input change → 월요일로 정규화
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

  const teamNames = useMemo<string[]>(() => {
    if (!data) return [];
    const order: Record<string, number> = {
      구조1팀: 1,
      구조2팀: 2,
      구조3팀: 3,
      구조4팀: 4,
      진단팀: 5,
    };
    return Object.keys(data.teams).sort(
      (a, b) => (order[a] ?? 99) - (order[b] ?? 99),
    );
  }, [data]);

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">주간 업무일지</h1>
          <p className="mt-1 text-sm text-zinc-500">
            월~금 주차 단위 자동 집계 (KST). 데이터는 노션 미러 + employees DB 기반.
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
        <div className="space-y-4">
          {/* 요약 헤더 */}
          <div className="rounded-md border border-zinc-200 bg-zinc-50 p-3 text-sm dark:border-zinc-800 dark:bg-zinc-900">
            <div className="font-semibold">{formatPeriod(data)}</div>
            <div className="mt-1 text-zinc-600 dark:text-zinc-400">
              총원 <strong>{data.headcount.total}</strong>인
              {Object.entries(data.headcount.by_occupation).map(([k, v]) => (
                <span key={k}> · {k} {v}</span>
              ))}
              {data.headcount.resigned_this_week.length > 0 && (
                <span className="ml-2 text-red-600">
                  퇴사 {data.headcount.resigned_this_week.length} (
                  {data.headcount.resigned_this_week.join(", ")})
                </span>
              )}
            </div>
          </div>

          {/* 카운트 요약 4 박스 */}
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <SummaryBox label="이번 주 영업" value={data.sales.length} />
            <SummaryBox label="이번 주 신규" value={data.new_projects.length} />
            <SummaryBox label="이번 주 완료" value={data.completed.length} />
            <SummaryBox
              label="진행 중 (전 팀)"
              value={Object.values(data.teams).reduce(
                (a, t) => a + t.length,
                0,
              )}
            />
          </div>

          {/* 영업 미리보기 */}
          {data.sales.length > 0 && (
            <Section title="■ 영업">
              <SimpleTable
                cols={["코드", "내용", "프로젝트", "발주처", "단계", "견적가"]}
                rows={data.sales.map((s) => [
                  s.code,
                  s.category.join("/"),
                  s.name,
                  s.client,
                  s.stage,
                  s.estimated_amount
                    ? `₩${s.estimated_amount.toLocaleString()}`
                    : "",
                ])}
              />
            </Section>
          )}

          {/* 완료/신규 */}
          <div className="grid gap-3 lg:grid-cols-2">
            {data.completed.length > 0 && (
              <Section title="■ 이번 주 완료">
                <SimpleTable
                  cols={["코드", "프로젝트명", "팀"]}
                  rows={data.completed.map((c) => [
                    c.code,
                    c.name,
                    c.teams.join(", "),
                  ])}
                />
              </Section>
            )}
            {data.new_projects.length > 0 && (
              <Section title="■ 이번 주 신규 (휴리스틱)">
                <SimpleTable
                  cols={["코드", "프로젝트명", "단계"]}
                  rows={data.new_projects.map((n) => [n.code, n.name, n.stage])}
                />
              </Section>
            )}
          </div>

          {/* 팀별 진행 */}
          {teamNames.map((team) => (
            <Section key={team} title={`■ ${team} (${data.teams[team].length}건)`}>
              <SimpleTable
                cols={["코드", "프로젝트명", "PM", "단계", "진행률", "마감"]}
                rows={data.teams[team].map((r) => [
                  r.code,
                  r.name,
                  r.pm,
                  r.stage,
                  `${Math.round(r.progress * 100)}%`,
                  r.end_date ?? "",
                ])}
              />
            </Section>
          ))}

          <p className="text-xs text-zinc-400">
            ※ 1차 버전 — 공지/교육/금주예정사항/날인대장은 후속 PR에서 채워집니다.
          </p>
        </div>
      )}
    </div>
  );
}

function SummaryBox({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="text-xs text-zinc-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold">{value}</div>
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
      <h2 className="text-sm font-semibold text-emerald-700 dark:text-emerald-400">
        {title}
      </h2>
      {children}
    </section>
  );
}

function SimpleTable({
  cols,
  rows,
}: {
  cols: string[];
  rows: (string | number)[][];
}) {
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
                <td key={j} className="px-2 py-1">
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
