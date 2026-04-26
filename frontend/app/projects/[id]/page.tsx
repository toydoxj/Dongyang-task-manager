"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";

import LifecycleTimeline from "@/components/project/LifecycleTimeline";
import ProgressOverview from "@/components/project/ProgressOverview";
import ProjectCashflowChart from "@/components/project/ProjectCashflowChart";
import ProjectHeader from "@/components/project/ProjectHeader";
import TaskKanban from "@/components/project/TaskKanban";
import { getCashflow, getProject, listTasks } from "@/lib/api";
import type { CashflowEntry, Project, Task } from "@/lib/domain";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function ProjectDetailPage({ params }: PageProps) {
  const { id } = use(params);
  const [project, setProject] = useState<Project | null>(null);
  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [cashflow, setCashflow] = useState<CashflowEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [p, ts, cf] = await Promise.all([
        getProject(id),
        listTasks({ project_id: id }),
        getCashflow({ project_id: id }),
      ]);
      setProject(p);
      setTasks(ts.items);
      setCashflow(cf.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "데이터 로딩 실패");
    }
  }, [id]);

  useEffect(() => {
    void (async () => {
      await load();
    })();
  }, [load]);

  if (error) {
    return (
      <div className="space-y-3">
        <Link href="/projects" className="text-xs text-zinc-500 hover:underline">
          ← 프로젝트 목록
        </Link>
        <div className="rounded-md border border-red-500/40 bg-red-500/5 p-3 text-sm text-red-400">
          {error}
        </div>
      </div>
    );
  }

  if (!project || !tasks || !cashflow) {
    return (
      <div className="space-y-4">
        <Link href="/projects" className="text-xs text-zinc-500 hover:underline">
          ← 프로젝트 목록
        </Link>
        <div className="h-32 animate-pulse rounded-xl border border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900" />
        <div className="h-32 animate-pulse rounded-xl border border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900" />
        <div className="h-72 animate-pulse rounded-xl border border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Link href="/projects" className="text-xs text-zinc-500 hover:underline">
          ← 프로젝트 목록
        </Link>
        {project.url && (
          <a
            href={project.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-zinc-500 hover:underline"
          >
            노션에서 열기 ↗
          </a>
        )}
      </div>

      <ProjectHeader project={project} />
      <LifecycleTimeline project={project} tasks={tasks} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ProgressOverview project={project} tasks={tasks} />
        <ProjectCashflowChart project={project} entries={cashflow} />
      </div>

      <TaskKanban tasks={tasks} onChanged={() => void load()} />
    </div>
  );
}
