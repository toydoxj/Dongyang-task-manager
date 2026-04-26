"use client";

import { differenceInDays, format, parseISO } from "date-fns";

import type { Project, Task } from "@/lib/domain";
import { formatDate } from "@/lib/format";

interface Props {
  project: Project;
  tasks: Task[];
}

/**
 * 단순 SVG 타임라인. (vis-timeline 의존성을 피하고 가벼움)
 * - 가로 축: 수주(시작일) → 계약기간 → 완료
 * - 현재 시점 표시
 * - 업무TASK 들의 기간(start~end)을 작은 막대로 오버레이
 */
export default function LifecycleTimeline({ project, tasks }: Props) {
  // 축 범위 결정
  const dates = [
    project.start_date,
    project.contract_start,
    project.contract_end,
    project.end_date,
    ...tasks.flatMap((t) => [t.start_date, t.end_date, t.actual_end_date]),
  ].filter((d): d is string => !!d);

  if (dates.length < 2) {
    return (
      <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
        <h3 className="mb-2 text-sm font-semibold">라이프사이클</h3>
        <p className="py-6 text-center text-xs text-zinc-500">
          날짜 정보가 부족합니다 (시작일·계약기간·완료일 중 최소 2개 필요).
        </p>
      </div>
    );
  }

  const min = dates.reduce((a, b) => (a < b ? a : b));
  const max = dates.reduce((a, b) => (a > b ? a : b));
  const minDate = parseISO(min);
  const maxDate = parseISO(max);
  const totalDays = Math.max(1, differenceInDays(maxDate, minDate));

  const ratio = (iso: string | null) => {
    if (!iso) return null;
    const d = parseISO(iso);
    return Math.max(0, Math.min(1, differenceInDays(d, minDate) / totalDays));
  };

  const startR = ratio(project.start_date);
  const csR = ratio(project.contract_start);
  const ceR = ratio(project.contract_end);
  const endR = ratio(project.end_date);
  const nowR = ratio(new Date().toISOString().slice(0, 10));

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <header className="mb-4 flex items-center justify-between">
        <h3 className="text-sm font-semibold">라이프사이클</h3>
        <p className="text-[10px] text-zinc-500">
          {format(minDate, "yyyy.MM.dd")} ~ {format(maxDate, "yyyy.MM.dd")}
        </p>
      </header>

      <div className="relative h-24">
        {/* 메인 축 */}
        <div className="absolute left-0 right-0 top-10 h-1 rounded-full bg-zinc-200 dark:bg-zinc-800" />

        {/* 계약기간 강조 */}
        {csR != null && ceR != null && (
          <div
            className="absolute top-10 h-1 rounded-full bg-blue-500/70"
            style={{
              left: `${csR * 100}%`,
              width: `${Math.max(0, (ceR - csR) * 100)}%`,
            }}
            title={`계약기간 ${formatDate(project.contract_start)} ~ ${formatDate(project.contract_end)}`}
          />
        )}

        {/* TASK 점 */}
        {tasks.map((t) => {
          const r = ratio(t.actual_end_date) ?? ratio(t.end_date) ?? ratio(t.start_date);
          if (r == null) return null;
          return (
            <div
              key={t.id}
              className="absolute top-9 h-3 w-1.5 -translate-x-1/2 rounded-sm bg-zinc-400/80 dark:bg-zinc-500/80"
              style={{ left: `${r * 100}%` }}
              title={`${t.title} (${t.status})`}
            />
          );
        })}

        {/* 현재 */}
        {nowR != null && nowR > 0 && nowR < 1 && (
          <div
            className="absolute top-7 h-7 w-0.5 -translate-x-1/2 bg-red-500"
            style={{ left: `${nowR * 100}%` }}
          >
            <span className="absolute -top-5 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-red-500 px-1.5 py-0.5 text-[9px] text-white">
              오늘
            </span>
          </div>
        )}

        {/* 마커 라벨 */}
        {startR != null && (
          <Marker
            x={startR}
            label="수주"
            date={formatDate(project.start_date)}
            color="bg-emerald-500"
          />
        )}
        {endR != null && (
          <Marker
            x={endR}
            label="완료"
            date={formatDate(project.end_date)}
            color="bg-zinc-700 dark:bg-zinc-300"
          />
        )}
      </div>
    </div>
  );
}

function Marker({
  x,
  label,
  date,
  color,
}: {
  x: number;
  label: string;
  date: string;
  color: string;
}) {
  return (
    <div className="absolute top-9" style={{ left: `${x * 100}%` }}>
      <div className={`h-3 w-3 -translate-x-1/2 rounded-full border-2 border-white ${color} dark:border-zinc-900`} />
      <p className="absolute top-4 -translate-x-1/2 whitespace-nowrap text-[10px] text-zinc-600 dark:text-zinc-400">
        {label}
      </p>
      <p className="absolute top-9 -translate-x-1/2 whitespace-nowrap text-[9px] text-zinc-400">
        {date}
      </p>
    </div>
  );
}
