"use client";

import Link from "next/link";
import { useState } from "react";
import { useSWRConfig } from "swr";

import LifecycleTimeline from "@/components/project/LifecycleTimeline";
import ProjectCashflowChart from "@/components/project/ProjectCashflowChart";
import ProjectEditModal from "@/components/project/ProjectEditModal";
import ProjectHeader from "@/components/project/ProjectHeader";
import TaskCreateModal from "@/components/project/TaskCreateModal";
import TaskKanban from "@/components/project/TaskKanban";
import LoadingState from "@/components/ui/LoadingState";
import { keys, useCashflow, useProject, useTasks } from "@/lib/hooks";

export default function ProjectClient({ id }: { id: string }) {
  const { mutate } = useSWRConfig();
  const [createOpen, setCreateOpen] = useState(false);
  const [createStatus, setCreateStatus] = useState<string | undefined>(undefined);
  const [editOpen, setEditOpen] = useState(false);

  const { data: project, error: projectErr } = useProject(id);
  const { data: tasksData, error: tasksErr } = useTasks({ project_id: id });
  const { data: cashflowData, error: cashflowErr } = useCashflow({
    project_id: id,
  });

  const error = projectErr ?? tasksErr ?? cashflowErr;
  const tasks = tasksData?.items;
  const cashflow = cashflowData?.items;

  const refreshTasks = (): void => {
    void mutate(keys.tasks({ project_id: id }));
  };

  const openCreate = (status?: string): void => {
    setCreateStatus(status);
    setCreateOpen(true);
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
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setEditOpen(true)}
            className="rounded-md border border-zinc-300 px-2.5 py-1 text-xs hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
          >
            편집
          </button>
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
      </div>

      <ProjectHeader project={project} />
      <LifecycleTimeline project={project} tasks={tasks} />

      <TaskKanban tasks={tasks} onChanged={refreshTasks} onCreate={openCreate} />

      <ProjectCashflowChart project={project} entries={cashflow} />

      <TaskCreateModal
        open={createOpen}
        projectId={id}
        initialStatus={createStatus}
        onClose={() => setCreateOpen(false)}
        onCreated={refreshTasks}
      />

      {editOpen && (
        <ProjectEditModal
          project={project}
          onClose={() => setEditOpen(false)}
          onSaved={() => {
            void mutate(keys.project(id));
          }}
        />
      )}
    </div>
  );
}
