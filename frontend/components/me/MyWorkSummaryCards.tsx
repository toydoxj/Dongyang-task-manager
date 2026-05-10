"use client";

import type { Project, Task } from "@/lib/domain";
import type { SealRequestItem } from "@/lib/api";

interface Props {
  /** 본인(또는 ?as 대상) 이름 — 날인 검토자 매칭에 사용. null이면 0건 표시. */
  myName: string | null;
  /** 본인 담당 진행중·대기 프로젝트. */
  projects: Project[];
  /** 본인 담당 TASK (완료 cutoff 적용 후). */
  tasks: Task[];
  /** 전체 날인요청 — 본인 검토자 매칭은 컴포넌트 내부에서 필터. */
  sealRequests: SealRequestItem[];
}

const PENDING_SEAL_STATUSES = new Set(["1차검토 중", "2차검토 중"]);

function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function startOfWeekMonday(d: Date): Date {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  const day = x.getDay() || 7;
  x.setDate(x.getDate() - (day - 1));
  return x;
}

export default function MyWorkSummaryCards({
  myName,
  projects,
  tasks,
  sealRequests,
}: Props) {
  const today = new Date();
  const todayStr = ymd(today);
  const weekStart = startOfWeekMonday(today);
  const weekEnd = new Date(weekStart);
  weekEnd.setDate(weekEnd.getDate() + 7);
  const weekEndStr = ymd(weekEnd);

  const dueDateStr = (t: Task): string | null =>
    t.end_date ? t.end_date.slice(0, 10) : null;

  // 1) 오늘 마감 — 미완료 + end_date == today
  const dueToday = tasks.filter(
    (t) => t.status !== "완료" && dueDateStr(t) === todayStr,
  ).length;

  // 2) 이번 주 마감 — 미완료 + end_date in [today, weekEnd) (오늘 포함)
  const dueThisWeek = tasks.filter((t) => {
    if (t.status === "완료") return false;
    const d = dueDateStr(t);
    return d != null && d >= todayStr && d < weekEndStr;
  }).length;

  // 3) 지연 — 미완료 + end_date < today
  const overdue = tasks.filter((t) => {
    if (t.status === "완료") return false;
    const d = dueDateStr(t);
    return d != null && d < todayStr;
  }).length;

  // 4) 승인·피드백 대기 — 본인이 검토자(lead/admin)인 검토중 날인
  const myReviewPending = myName
    ? sealRequests.filter(
        (s) =>
          PENDING_SEAL_STATUSES.has(s.status) &&
          (s.lead_handler === myName || s.admin_handler === myName),
      ).length
    : 0;

  // 5) 진행 프로젝트 수 (이미 mine 기준)
  const projectCount = projects.length;

  return (
    <section className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
      <Card label="오늘 마감" value={dueToday} hint={todayStr} tone={dueToday > 0 ? "warn" : "neutral"} />
      <Card label="이번 주 마감" value={dueThisWeek} hint={`~ ${ymd(new Date(weekEnd.getTime() - 86400000))}`} tone={dueThisWeek > 0 ? "warn" : "neutral"} />
      <Card label="지연" value={overdue} hint="마감 경과" tone={overdue > 0 ? "danger" : "neutral"} />
      <Card label="승인·피드백 대기" value={myReviewPending} hint="내가 검토자" tone={myReviewPending > 0 ? "warn" : "neutral"} />
      <Card label="진행 프로젝트" value={projectCount} hint="진행중·대기" tone="neutral" />
    </section>
  );
}

type Tone = "neutral" | "warn" | "danger";

function Card({
  label,
  value,
  hint,
  tone = "neutral",
}: {
  label: string;
  value: number;
  hint: string;
  tone?: Tone;
}) {
  const toneClass =
    tone === "danger"
      ? "text-red-600 dark:text-red-400"
      : tone === "warn"
        ? "text-amber-600 dark:text-amber-400"
        : "text-zinc-900 dark:text-zinc-100";
  return (
    <div className="flex flex-col gap-0.5 rounded-xl border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900">
      <span className="text-[11px] font-medium text-zinc-500">{label}</span>
      <span className={`text-xl font-semibold ${toneClass}`}>{value}</span>
      <span className="truncate text-[10px] text-zinc-500">{hint}</span>
    </div>
  );
}
