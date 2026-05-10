"use client";

import Link from "next/link";

import { CTA } from "@/lib/cta";
import type { Project, Task } from "@/lib/domain";
import type { SealRequestItem } from "@/lib/api";

interface Props {
  projects: Project[];
  tasks: Task[];
  sealRequests: SealRequestItem[];
}

const STALE_PROJECT_DAYS = 90;
const ACTION_DUE_SOON_DAYS = 3;
const STALE_TASK_DAYS = 60;
const PENDING_SEAL_STATUSES = new Set(["1차검토 중", "2차검토 중"]);

function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export default function PriorityActionsPanel({
  projects,
  tasks,
  sealRequests,
}: Props) {
  const today = new Date();
  const todayStr = ymd(today);

  const staleCutoff = new Date(today);
  staleCutoff.setDate(staleCutoff.getDate() - STALE_PROJECT_DAYS);
  const staleCutoffStr = ymd(staleCutoff);

  const dueSoonEnd = new Date(today);
  dueSoonEnd.setDate(dueSoonEnd.getDate() + ACTION_DUE_SOON_DAYS);
  const dueSoonEndStr = ymd(dueSoonEnd);

  const staleTaskCutoff = new Date(today);
  staleTaskCutoff.setDate(staleTaskCutoff.getDate() - STALE_TASK_DAYS);
  const staleTaskCutoffStr = ymd(staleTaskCutoff);

  // 1. 장기 정체 프로젝트
  const stalledProjects = projects
    .filter(
      (p) =>
        (p.stage === "진행중" || p.stage === "대기") &&
        p.start_date != null &&
        p.start_date.slice(0, 10) <= staleCutoffStr,
    )
    .sort((a, b) =>
      (a.start_date ?? "").localeCompare(b.start_date ?? ""),
    );

  // 2. 승인 지연 날인 (제출예정일 지났는데 검토중)
  const overdueSeals = sealRequests
    .filter(
      (s) =>
        PENDING_SEAL_STATUSES.has(s.status) &&
        s.due_date != null &&
        s.due_date.slice(0, 10) < todayStr,
    )
    .sort((a, b) => (a.due_date ?? "").localeCompare(b.due_date ?? ""));

  // 3. 마감 임박 TASK (오늘 ~ +3일)
  const dueSoonTasks = tasks
    .filter(
      (t) =>
        t.status !== "완료" &&
        t.end_date != null &&
        t.end_date.slice(0, 10) >= todayStr &&
        t.end_date.slice(0, 10) <= dueSoonEndStr,
    )
    .sort((a, b) => (a.end_date ?? "").localeCompare(b.end_date ?? ""));

  // 4. 담당 편중 팀 (진행중 프로젝트 수)
  const teamLoad: Record<string, number> = {};
  for (const p of projects) {
    if (p.stage !== "진행중") continue;
    for (const t of p.teams) {
      teamLoad[t] = (teamLoad[t] ?? 0) + 1;
    }
  }
  const sortedTeams = Object.entries(teamLoad).sort(([, a], [, b]) => b - a);
  const topTeam = sortedTeams[0];

  // 5. 오래 멈춘 TASK (시작 전 + 60일 이상 안 움직임)
  const stuckTasks = tasks
    .filter(
      (t) =>
        t.status === "시작 전" &&
        t.created_time != null &&
        t.created_time.slice(0, 10) <= staleTaskCutoffStr,
    )
    .sort((a, b) =>
      (a.created_time ?? "").localeCompare(b.created_time ?? ""),
    );

  const items: ActionItem[] = [
    {
      icon: "⏰",
      title: `장기 정체 프로젝트 (${STALE_PROJECT_DAYS}일 이상)`,
      count: stalledProjects.length,
      preview: stalledProjects[0]?.name,
      ctaLabel: CTA.openProject,
      ctaHref:
        stalledProjects.length === 1
          ? `/project?id=${stalledProjects[0].id}`
          : "/projects",
    },
    {
      icon: "🔖",
      title: "승인 지연 날인 (제출예정일 경과)",
      count: overdueSeals.length,
      preview: overdueSeals[0]?.title,
      ctaLabel: CTA.viewSeals,
      ctaHref: "/seal-requests",
    },
    {
      icon: "📅",
      title: `마감 가까운 업무 (오늘 ~ +${ACTION_DUE_SOON_DAYS}일)`,
      count: dueSoonTasks.length,
      preview: dueSoonTasks[0]?.title,
      ctaLabel: CTA.viewMyTasks,
      ctaHref: "/me",
    },
    {
      icon: "👥",
      title: "담당 편중 팀",
      count: topTeam ? topTeam[1] : 0,
      preview: topTeam ? `${topTeam[0]} — 진행중 ${topTeam[1]}건` : undefined,
      ctaLabel: CTA.viewLoad,
      ctaHref: "/admin/employee-work",
    },
    {
      icon: "🐢",
      title: `오래 멈춘 TASK (시작 전 ${STALE_TASK_DAYS}일 이상)`,
      count: stuckTasks.length,
      preview: stuckTasks[0]?.title,
      ctaLabel: CTA.viewMyTasks,
      ctaHref: "/me",
    },
  ];

  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <header className="mb-3">
        <h2 className="text-sm font-semibold">지금 처리할 것</h2>
        <p className="text-[11px] text-zinc-500">
          정체·지연·과부하·임박 항목을 모은 핫스팟. 항목 옆 버튼으로 바로 이동.
        </p>
      </header>
      <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
        {items.map((it) => (
          <ActionRow key={it.title} item={it} />
        ))}
      </ul>
    </section>
  );
}

interface ActionItem {
  icon: string;
  title: string;
  count: number;
  preview?: string;
  ctaLabel: string;
  ctaHref: string;
}

function ActionRow({ item }: { item: ActionItem }) {
  const isEmpty = item.count === 0;
  return (
    <li className="flex items-center gap-3 py-2.5">
      <span className="text-base leading-none">{item.icon}</span>
      <div className="min-w-0 flex-1">
        <p className="flex items-center gap-2 text-sm">
          <span className="font-medium text-zinc-800 dark:text-zinc-200">
            {item.title}
          </span>
          <span
            className={
              isEmpty
                ? "rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] font-medium text-zinc-500 dark:bg-zinc-800"
                : "rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-700 dark:bg-amber-500/20 dark:text-amber-300"
            }
          >
            {item.count}건
          </span>
        </p>
        {item.preview && (
          <p className="mt-0.5 truncate text-[11px] text-zinc-500">
            {item.preview}
          </p>
        )}
      </div>
      {!isEmpty && (
        <Link
          href={item.ctaHref}
          className="shrink-0 rounded-md border border-zinc-300 bg-white px-2.5 py-1 text-[11px] font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800"
        >
          {item.ctaLabel}
        </Link>
      )}
    </li>
  );
}
