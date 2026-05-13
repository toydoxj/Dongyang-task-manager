"use client";

import Link from "next/link";

import { CTA } from "@/lib/cta";
import type { DashboardActions } from "@/lib/api";

const STALE_PROJECT_DAYS = 90;
const ACTION_DUE_SOON_DAYS = 3;
const STALE_TASK_DAYS = 60;

interface Props {
  actions: DashboardActions;
}

export default function PriorityActionsPanel({ actions }: Props) {
  const items: ActionRowItem[] = [
    {
      icon: "⏰",
      title: `장기 정체 프로젝트 (${STALE_PROJECT_DAYS}일 이상)`,
      count: actions.stalled_projects.count,
      preview: actions.stalled_projects.preview,
      ctaLabel: CTA.openProject,
      ctaHref: "/projects",
    },
    {
      icon: "🔖",
      title: "승인 지연 날인 (제출예정일 경과)",
      count: actions.overdue_seals.count,
      preview: actions.overdue_seals.preview,
      ctaLabel: CTA.viewSeals,
      ctaHref: "/seal-requests",
    },
    {
      icon: "📅",
      title: `마감 가까운 업무 (오늘 ~ +${ACTION_DUE_SOON_DAYS}일)`,
      count: actions.due_soon_tasks.count,
      preview: actions.due_soon_tasks.preview,
      ctaLabel: CTA.viewMyTasks,
      ctaHref: "/me",
    },
    {
      icon: "👥",
      title: "담당 편중 팀",
      count: actions.overloaded_team.count,
      preview: actions.overloaded_team.preview,
      ctaLabel: CTA.viewLoad,
      ctaHref: "/admin/employee-work",
    },
    {
      icon: "🐢",
      title: `오래 멈춘 TASK (시작 전 ${STALE_TASK_DAYS}일 이상)`,
      count: actions.stuck_tasks.count,
      preview: actions.stuck_tasks.preview,
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

interface ActionRowItem {
  icon: string;
  title: string;
  count: number;
  preview?: string;
  ctaLabel: string;
  ctaHref: string;
}

function ActionRow({ item }: { item: ActionRowItem }) {
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
