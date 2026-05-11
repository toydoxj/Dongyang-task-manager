/**
 * /me 페이지 전용 pure helpers.
 * PR-AK — app/me/page.tsx에서 추출 (외과적 변경 / 동작 동일).
 */

import type { Project, Task } from "@/lib/domain";
import { formatDate } from "@/lib/format";

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
  const active: Project[] = [];
  const idle: Project[] = [];
  for (const p of projects) {
    const projTasks = tasks.filter((t) => taskBelongsTo(t, p.id));
    const hasThisWeek = projTasks.some((t) => taskInWeek(t, weekStart, weekEnd));
    if (hasThisWeek) active.push(p);
    else idle.push(p);
  }
  return { active, idle };
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
