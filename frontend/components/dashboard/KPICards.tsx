"use client";

import Link from "next/link";

import type { DashboardSummary } from "@/lib/api";
import { formatWon } from "@/lib/format";

const STALE_DAYS = 90;
const DUE_SOON_DAYS = 7;

interface Props {
  summary: DashboardSummary;
}

export default function KPICards({ summary }: Props) {
  const weekNet = summary.week_income - summary.week_expense;

  return (
    <section className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
      <KpiCard
        label="진행중"
        value={summary.in_progress_count}
        hint="현재 진행 단계"
        href="/projects"
      />
      <KpiCard
        label="장기 정체"
        value={summary.stalled_count}
        hint={`${STALE_DAYS}일 이상 진행중·대기`}
        href="/projects"
        tone={summary.stalled_count > 0 ? "warn" : "neutral"}
      />
      <KpiCard
        label="마감 임박 TASK"
        value={summary.due_soon_tasks}
        hint={`오늘 ~ +${DUE_SOON_DAYS}일`}
        href="/me"
        tone={summary.due_soon_tasks > 0 ? "warn" : "neutral"}
      />
      <KpiCard
        label="승인 대기 날인"
        value={summary.pending_seal_count}
        hint="1차 / 2차 검토중"
        href="/seal-requests"
        tone={summary.pending_seal_count > 0 ? "warn" : "neutral"}
      />
      <KpiCard
        label="이번 주 순현금"
        value={formatWon(weekNet, true)}
        hint={`수입 ${formatWon(summary.week_income, true)} / 지출 ${formatWon(summary.week_expense, true)}`}
        href="/admin/incomes"
        tone={weekNet >= 0 ? "good" : "warn"}
      />
      <KpiCard
        label="최다 부하 팀"
        value={summary.top_team ? summary.top_team.name : "—"}
        hint={
          summary.top_team
            ? `진행중 ${summary.top_team.count}건`
            : "진행중 프로젝트 없음"
        }
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
