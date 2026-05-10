"use client";

import Link from "next/link";

import type { CashflowEntry, Project, Task } from "@/lib/domain";
import { formatWon } from "@/lib/format";
import type { SealRequestItem } from "@/lib/api";

interface Props {
  projects: Project[];
  tasks: Task[];
  incomes: CashflowEntry[];
  expenses: CashflowEntry[];
  sealRequests: SealRequestItem[];
}

// 임계값 (RecentAndStaleProjects · USER_MANUAL 컨벤션과 통일)
const STALE_DAYS = 90;
const DUE_SOON_DAYS = 7;
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

export default function KPICards({
  projects,
  tasks,
  incomes,
  expenses,
  sealRequests,
}: Props) {
  const today = new Date();
  const todayStr = ymd(today);

  const weekStart = startOfWeekMonday(today);
  const weekEnd = new Date(weekStart);
  weekEnd.setDate(weekEnd.getDate() + 7);
  const weekStartStr = ymd(weekStart);
  const weekEndStr = ymd(weekEnd);

  const staleCutoff = new Date(today);
  staleCutoff.setDate(staleCutoff.getDate() - STALE_DAYS);
  const staleCutoffStr = ymd(staleCutoff);

  const dueSoonEnd = new Date(today);
  dueSoonEnd.setDate(dueSoonEnd.getDate() + DUE_SOON_DAYS);
  const dueSoonEndStr = ymd(dueSoonEnd);

  // 1. 진행중
  const inProgressCount = projects.filter((p) => p.stage === "진행중").length;

  // 2. 장기 정체 (진행중·대기 + 90일 이상)
  const stalledCount = projects.filter(
    (p) =>
      (p.stage === "진행중" || p.stage === "대기") &&
      p.start_date != null &&
      p.start_date.slice(0, 10) <= staleCutoffStr,
  ).length;

  // 3. 마감 임박 TASK (today ~ +7일, 미완료)
  const dueSoonTasks = tasks.filter(
    (t) =>
      t.status !== "완료" &&
      t.end_date != null &&
      t.end_date.slice(0, 10) >= todayStr &&
      t.end_date.slice(0, 10) <= dueSoonEndStr,
  ).length;

  // 4. 승인 대기 날인 (1차/2차 검토중)
  const pendingSealCount = sealRequests.filter((s) =>
    PENDING_SEAL_STATUSES.has(s.status),
  ).length;

  // 5. 이번 주 수금-지출 (Mon~Sun)
  const inWeek = (entry: CashflowEntry): boolean =>
    entry.date != null &&
    entry.date.slice(0, 10) >= weekStartStr &&
    entry.date.slice(0, 10) < weekEndStr;
  const weekIncome = incomes.filter(inWeek).reduce((s, i) => s + i.amount, 0);
  const weekExpense = expenses.filter(inWeek).reduce((s, e) => s + e.amount, 0);
  const weekNet = weekIncome - weekExpense;

  // 6. 과부하 팀 (진행중 프로젝트 수 기준 1위)
  const teamLoad: Record<string, number> = {};
  for (const p of projects) {
    if (p.stage !== "진행중") continue;
    for (const t of p.teams) {
      teamLoad[t] = (teamLoad[t] ?? 0) + 1;
    }
  }
  const topTeam = Object.entries(teamLoad).sort(([, a], [, b]) => b - a)[0];

  return (
    <section className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
      <KpiCard
        label="진행중"
        value={inProgressCount}
        hint="현재 진행 단계"
        href="/projects"
      />
      <KpiCard
        label="장기 정체"
        value={stalledCount}
        hint={`${STALE_DAYS}일 이상 진행중·대기`}
        href="/projects"
        tone={stalledCount > 0 ? "warn" : "neutral"}
      />
      <KpiCard
        label="마감 임박 TASK"
        value={dueSoonTasks}
        hint={`오늘 ~ +${DUE_SOON_DAYS}일`}
        href="/me"
        tone={dueSoonTasks > 0 ? "warn" : "neutral"}
      />
      <KpiCard
        label="승인 대기 날인"
        value={pendingSealCount}
        hint="1차 / 2차 검토중"
        href="/seal-requests"
        tone={pendingSealCount > 0 ? "warn" : "neutral"}
      />
      <KpiCard
        label="이번 주 순현금"
        value={formatWon(weekNet, true)}
        hint={`수입 ${formatWon(weekIncome, true)} / 지출 ${formatWon(weekExpense, true)}`}
        href="/admin/incomes"
        tone={weekNet >= 0 ? "good" : "warn"}
      />
      <KpiCard
        label="최다 부하 팀"
        value={topTeam ? topTeam[0] : "—"}
        hint={topTeam ? `진행중 ${topTeam[1]}건` : "진행중 프로젝트 없음"}
        href="/projects"
      />
    </section>
  );
}

type Tone = "neutral" | "warn" | "good";

function KpiCard({
  label,
  value,
  hint,
  href,
  tone = "neutral",
}: {
  label: string;
  value: number | string;
  hint: string;
  href: string;
  tone?: Tone;
}) {
  const toneClass =
    tone === "warn"
      ? "text-amber-600 dark:text-amber-400"
      : tone === "good"
        ? "text-emerald-600 dark:text-emerald-400"
        : "text-zinc-900 dark:text-zinc-100";
  return (
    <Link
      href={href}
      className="flex flex-col gap-0.5 rounded-xl border border-zinc-200 bg-white p-3 transition-colors hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:bg-zinc-800"
    >
      <span className="text-[11px] font-medium text-zinc-500">{label}</span>
      <span className={`truncate text-xl font-semibold ${toneClass}`}>
        {value}
      </span>
      <span className="truncate text-[10px] text-zinc-500">{hint}</span>
    </Link>
  );
}
