"use client";

import Link from "next/link";

import { useAuth } from "@/components/AuthGuard";
import UpcomingDeadlines from "@/components/me/UpcomingDeadlines";
import ProjectCard from "@/components/projects/ProjectCard";
import LoadingState from "@/components/ui/LoadingState";
import type { Task } from "@/lib/domain";
import { dDayLabel, formatDate, formatPercent } from "@/lib/format";
import { useProjects, useTasks } from "@/lib/hooks";
import { cn } from "@/lib/utils";

export default function MyPage() {
  const { user } = useAuth();
  const { data: projectData, error: projectErr } = useProjects(
    user?.name ? { mine: true } : undefined,
  );
  const { data: tasksData, error: tasksErr } = useTasks(
    user?.name ? { mine: true } : undefined,
  );

  const error = projectErr ?? tasksErr;
  const projects = projectData?.items;
  const tasks = tasksData?.items;

  if (!user?.name) {
    return (
      <div className="space-y-3">
        <h1 className="text-2xl font-semibold">내 업무</h1>
        <p className="rounded-md border border-yellow-500/40 bg-yellow-500/5 p-3 text-sm text-yellow-400">
          본인 이름이 등록되어 있지 않아 담당 프로젝트를 조회할 수 없습니다.
          <br />
          노션 담당자 옵션과 일치하는 이름으로 프로필을 설정해주세요.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">내 업무</h1>
        <p className="mt-1 text-sm text-zinc-500">
          {user.name} 님이 담당자로 지정된 프로젝트와 업무 TASK 입니다.
        </p>
      </header>

      {error && (
        <div className="rounded-md border border-red-500/40 bg-red-500/5 p-3 text-sm text-red-400">
          {error instanceof Error ? error.message : String(error)}
        </div>
      )}

      <section>
        <h2 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
          오늘 할 일 (진행 중·시작 전, 마감 임박순)
        </h2>
        {tasks == null ? (
          <LoadingState message="내 업무 TASK 불러오는 중" height="h-32" />
        ) : (
          <TodayTasks tasks={tasks} />
        )}
      </section>

      <section>
        <h2 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
          마감 임박 프로젝트
        </h2>
        {projects == null ? (
          <LoadingState message="프로젝트 마감일 분석 중" height="h-32" />
        ) : (
          <UpcomingDeadlines projects={projects} />
        )}
      </section>

      <section>
        <h2 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
          담당 프로젝트 ({projects?.length ?? "—"})
        </h2>
        {projects == null ? (
          <LoadingState message="담당 프로젝트 불러오는 중" height="h-32" />
        ) : projects.length === 0 ? (
          <p className="rounded-md border border-zinc-200 bg-white p-4 text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900">
            담당으로 지정된 프로젝트가 없습니다.
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            {projects.map((p) => (
              <ProjectCard key={p.id} project={p} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function TodayTasks({ tasks }: { tasks: Task[] }) {
  const open = tasks.filter((t) => t.status !== "완료");
  open.sort((a, b) => {
    if (!a.end_date && !b.end_date) return 0;
    if (!a.end_date) return 1;
    if (!b.end_date) return -1;
    return a.end_date.localeCompare(b.end_date);
  });
  const top = open.slice(0, 12);

  if (top.length === 0) {
    return (
      <p className="rounded-md border border-zinc-200 bg-white p-4 text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900">
        오늘 처리할 업무가 없습니다. 🎉
      </p>
    );
  }

  return (
    <ul className="divide-y divide-zinc-200 rounded-xl border border-zinc-200 bg-white dark:divide-zinc-800 dark:border-zinc-800 dark:bg-zinc-900">
      {top.map((t) => {
        const projId = t.project_ids[0];
        const node = (
          <div className="flex items-center justify-between gap-3 px-4 py-2.5">
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium" title={t.title}>
                {t.title || "(제목 없음)"}
              </p>
              <p className="mt-0.5 text-[11px] text-zinc-500">
                {t.status} · {formatPercent(t.progress)} · 마감 {formatDate(t.end_date)}
              </p>
            </div>
            <span
              className={cn(
                "shrink-0 rounded-md px-2 py-0.5 text-[10px] font-medium",
                statusBadgeColor(t),
              )}
            >
              {dDayLabel(t.end_date) || "—"}
            </span>
          </div>
        );
        return (
          <li key={t.id}>
            {projId ? (
              <Link
                href={`/projects/${projId}`}
                className="block hover:bg-zinc-50 dark:hover:bg-zinc-800/50"
              >
                {node}
              </Link>
            ) : (
              node
            )}
          </li>
        );
      })}
    </ul>
  );
}

function statusBadgeColor(t: Task): string {
  if (!t.end_date) return "bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300";
  const days = Math.floor(
    (new Date(t.end_date).getTime() - Date.now()) / 86400000,
  );
  if (days < 0) return "bg-red-500/20 text-red-400";
  if (days <= 3) return "bg-orange-500/20 text-orange-400";
  if (days <= 7) return "bg-yellow-500/20 text-yellow-400";
  return "bg-emerald-500/20 text-emerald-400";
}
