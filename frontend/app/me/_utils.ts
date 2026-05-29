/**
 * /me 페이지 전용 pure helpers.
 * PR-AK — app/me/page.tsx에서 추출 (외과적 변경 / 동작 동일).
 */

import type { Project, Task } from "@/lib/domain";
import { formatDate } from "@/lib/format";

export const SCHEDULE_LOOKBACK_DAYS = 14;
export const SCHEDULE_LOOKAHEAD_DAYS = 60;
export const SCHEDULE_BUCKET_LIMIT = 80;
export const SCHEDULE_BUCKETS = ["외근", "출장", "파견", "휴가"] as const;

export type ScheduleBucket = (typeof SCHEDULE_BUCKETS)[number];

/**
 * 완료된 TASK는 이번주 월요일 00:00 KST 기준 -14일 이후만 표시.
 * 그보다 오래된 완료는 hide. 완료가 아닌 task는 통과.
 * 시점(actual_end_date/last_edited_time) 미상이면 안전하게 통과.
 *
 * PR-FI/9: /me 4탭(할일/일정/기타업무/담당프로젝트/내영업) 모두 동일 적용.
 * 기존엔 page.tsx에서만 적용 → ProjectTaskRow/SaleTaskRow는 cutoff 없이 모든 완료 표시.
 */
export function filterCompletedByCutoff(tasks: Task[]): Task[] {
  const now = new Date();
  const dow = now.getDay(); // 0=Sun, 1=Mon..6=Sat
  const diffToMon = dow === 0 ? -6 : 1 - dow;
  const monday = new Date(now);
  monday.setDate(monday.getDate() + diffToMon);
  monday.setHours(0, 0, 0, 0);
  monday.setDate(monday.getDate() - 14);
  const cutoffMs = monday.getTime();
  return tasks.filter((t) => {
    if (t.status !== "완료") return true;
    const ref = t.actual_end_date ?? t.last_edited_time;
    if (!ref) return true;
    return new Date(ref).getTime() >= cutoffMs;
  });
}

export function formatRange(start: string | null, end: string | null): string {
  const fmt = (s: string | null): string => {
    if (!s) return "";
    if (s.includes("T")) {
      const d = new Date(s);
      if (Number.isNaN(d.getTime())) return s;
      return new Intl.DateTimeFormat("ko-KR", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
        timeZone: "Asia/Seoul",
      }).format(d);
    }
    return formatDate(s);
  };
  const a = fmt(start);
  const b = fmt(end);
  if (a && b && a === b) return a;
  if (a && b) return `${a} ~ ${b}`;
  return a || b || "—";
}

// 노션 page ID 는 응답에 따라 dash 유무가 섞여 있을 수 있어 비교 시 정규화 필요.
export function normId(s: string): string {
  return s.replace(/-/g, "").toLowerCase();
}

export function taskBelongsTo(t: Task, projectId: string): boolean {
  const target = normId(projectId);
  return t.project_ids.some((pid) => normId(pid) === target);
}

// 이번주 월요일 00:00 ~ 일요일 23:59 범위
export function thisWeekRange(): [Date, Date] {
  const now = new Date();
  const day = now.getDay(); // 일=0, 월=1, ..., 토=6
  const offsetToMon = day === 0 ? -6 : 1 - day;
  const mon = new Date(now);
  mon.setDate(now.getDate() + offsetToMon);
  mon.setHours(0, 0, 0, 0);
  const sun = new Date(mon);
  sun.setDate(mon.getDate() + 6);
  sun.setHours(23, 59, 59, 999);
  return [mon, sun];
}

export function taskInWeek(t: Task, weekStart: Date, weekEnd: Date): boolean {
  // 기간(start_date~end_date) 또는 actual_end_date 가 금주와 겹치면 true.
  // 양쪽 다 비어있으면 created_time 기반 보조 판정 (있으면).
  const candidates: Array<[string | null, string | null]> = [
    [t.start_date, t.end_date],
  ];
  if (t.actual_end_date) candidates.push([t.actual_end_date, t.actual_end_date]);
  for (const [s, e] of candidates) {
    if (!s && !e) continue;
    const start = s ? new Date(s) : new Date(e!);
    const end = e ? new Date(e) : start;
    end.setHours(23, 59, 59, 999);
    if (start <= weekEnd && end >= weekStart) return true;
  }
  return false;
}

export function splitByThisWeek(
  projects: Project[],
  tasks: Task[],
): { active: Project[]; idle: Project[] } {
  const [weekStart, weekEnd] = thisWeekRange();
  const activeProjectIds = new Set<string>();
  for (const t of tasks) {
    if (!taskInWeek(t, weekStart, weekEnd)) continue;
    for (const pid of t.project_ids) {
      activeProjectIds.add(normId(pid));
    }
  }

  const active: Project[] = [];
  const idle: Project[] = [];
  for (const p of projects) {
    if (activeProjectIds.has(normId(p.id))) active.push(p);
    else idle.push(p);
  }
  return { active, idle };
}

function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function addDays(base: Date, days: number): Date {
  const d = new Date(base);
  d.setDate(d.getDate() + days);
  return d;
}

function dateOnly(value: string | null | undefined): string | null {
  return value ? value.slice(0, 10) : null;
}

export function scheduleWindowFor(base = new Date()): {
  startYmd: string;
  endYmd: string;
} {
  return {
    startYmd: ymd(addDays(base, -SCHEDULE_LOOKBACK_DAYS)),
    endYmd: ymd(addDays(base, SCHEDULE_LOOKAHEAD_DAYS)),
  };
}

export function scheduleBucketForTask(
  t: Pick<Task, "activity" | "category">,
): ScheduleBucket | null {
  if (t.category === "휴가" || t.category === "휴가(연차)") return "휴가";
  if (t.activity === "파견" || t.category === "파견") return "파견";
  if (t.activity === "출장" || t.category === "출장") return "출장";
  if (t.activity === "외근" || t.category === "외근") return "외근";
  return null;
}

export function taskOverlapsScheduleWindow(
  t: Pick<Task, "actual_end_date" | "end_date" | "start_date">,
  startYmd: string,
  endYmd: string,
): boolean {
  const start = dateOnly(t.start_date) ?? dateOnly(t.end_date) ?? dateOnly(t.actual_end_date);
  const end = dateOnly(t.end_date) ?? start;
  if (!start) return true;
  return start <= endYmd && (end ?? start) >= startYmd;
}

export function shouldShowInScheduleTab(
  t: Pick<
    Task,
    "actual_end_date" | "activity" | "category" | "end_date" | "start_date"
  >,
  window = scheduleWindowFor(),
): boolean {
  return (
    scheduleBucketForTask(t) !== null &&
    taskOverlapsScheduleWindow(t, window.startYmd, window.endYmd)
  );
}

export function statusBadgeColor(t: Task): string {
  if (!t.end_date) return "bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300";
  const days = Math.floor(
    (new Date(t.end_date).getTime() - Date.now()) / 86400000,
  );
  if (days < 0) return "bg-red-500/20 text-red-400";
  if (days <= 3) return "bg-orange-500/20 text-orange-400";
  if (days <= 7) return "bg-yellow-500/20 text-yellow-400";
  return "bg-emerald-500/20 text-emerald-400";
}
