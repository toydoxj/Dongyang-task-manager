"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useSWRConfig } from "swr";

import LifecycleTimeline from "@/components/project/LifecycleTimeline";
import ProjectCashflowChart from "@/components/project/ProjectCashflowChart";
import ProjectEditModal from "@/components/project/ProjectEditModal";
import ProjectHeader from "@/components/project/ProjectHeader";
import SealRequestCreateModal from "@/components/project/SealRequestCreateModal";
import TaskCreateModal from "@/components/project/TaskCreateModal";
import TaskKanban from "@/components/project/TaskKanban";
import LoadingState from "@/components/ui/LoadingState";
import useSWR from "swr";

import { getProjectLog, listSealRequests } from "@/lib/api";
import { keys, useCashflow, useProject, useTasks } from "@/lib/hooks";

export default function ProjectClient({ id }: { id: string }) {
  const router = useRouter();
  const { mutate } = useSWRConfig();
  const [createOpen, setCreateOpen] = useState(false);
  const [createStatus, setCreateStatus] = useState<string | undefined>(undefined);
  const [editOpen, setEditOpen] = useState(false);
  const [sealOpen, setSealOpen] = useState(false);

  // 어디서 왔든 그 페이지로 돌아가기. history 없으면 /projects로 fallback.
  const goBack = (): void => {
    if (typeof window !== "undefined" && window.history.length > 1) {
      router.back();
    } else {
      router.push("/projects");
    }
  };
  const BackButton = (): React.ReactElement => (
    <button
      type="button"
      onClick={goBack}
      className="text-xs text-zinc-500 hover:underline"
    >
      ← 뒤로
    </button>
  );

  const { data: project, error: projectErr } = useProject(id);
  const { data: tasksData, error: tasksErr } = useTasks({ project_id: id });
  const { data: cashflowData, error: cashflowErr } = useCashflow({
    project_id: id,
  });
  const { data: sealsData } = useSWR(["seals", id], () =>
    listSealRequests({ projectId: id }),
  );
  const seals = sealsData?.items ?? [];
  const { data: logData } = useSWR(["project-log", id], () =>
    getProjectLog(id),
  );
  const logs = logData?.items ?? [];

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
        <BackButton />
        <div className="rounded-md border border-red-500/40 bg-red-500/5 p-3 text-sm text-red-400">
          {error instanceof Error ? error.message : String(error)}
        </div>
      </div>
    );
  }

  if (!project || !tasks || !cashflow) {
    return (
      <div className="space-y-4">
        <BackButton />
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
        <BackButton />
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setSealOpen(true)}
            className="rounded-md border border-zinc-300 px-2.5 py-1 text-xs hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
          >
            🔖 날인 요청
          </button>
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
      <LifecycleTimeline
        project={project}
        tasks={tasks}
        seals={seals}
        logs={logs}
      />

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

      <SealRequestCreateModal
        open={sealOpen}
        fixedProject={project}
        onClose={() => setSealOpen(false)}
        onCreated={() => setSealOpen(false)}
      />
    </div>
  );
}
