"use client";

import Link from "next/link";
import { use } from "react";
import { useSWRConfig } from "swr";

import LifecycleTimeline from "@/components/project/LifecycleTimeline";
import ProgressOverview from "@/components/project/ProgressOverview";
import ProjectCashflowChart from "@/components/project/ProjectCashflowChart";
import ProjectHeader from "@/components/project/ProjectHeader";
import TaskKanban from "@/components/project/TaskKanban";
import LoadingState from "@/components/ui/LoadingState";
import { keys, useCashflow, useProject, useTasks } from "@/lib/hooks";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function ProjectDetailPage({ params }: PageProps) {
  const { id } = use(params);
  const { mutate } = useSWRConfig();

  const { data: project, error: projectErr } = useProject(id);
  const { data: tasksData, error: tasksErr } = useTasks({ project_id: id });
  const { data: cashflowData, error: cashflowErr } = useCashflow({
    project_id: id,
  });

  const error = projectErr ?? tasksErr ?? cashflowErr;
  const tasks = tasksData?.items;
  const cashflow = cashflowData?.items;

  // TASK 갱신 후 캐시 무효화
  const refreshTasks = (): void => {
    void mutate(keys.tasks({ project_id: id }));
  };

  if (error) {
    return (
      <div className="space-y-3">
        <Link href="/projects" className="text-xs text-zinc-500 hover:underline">
          ← 프로젝트 목록
        </Link>
        <div className="rounded-md border border-red-500/40 bg-red-500/5 p-3 text-sm text-red-400">
          {error instanceof Error ? error.message : String(error)}
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
        <LoadingState
          message="프로젝트 상세 불러오는 중 (프로젝트·업무·현금흐름)"
          height="h-64"
        />
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

      <TaskKanban tasks={tasks} onChanged={refreshTasks} />
    </div>
  );
}
