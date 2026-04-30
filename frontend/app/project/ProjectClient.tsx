"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useSWRConfig } from "swr";

import LifecycleTimeline from "@/components/project/LifecycleTimeline";
import ProjectCashflowChart from "@/components/project/ProjectCashflowChart";
import ProjectEditModal from "@/components/project/ProjectEditModal";
import ProjectHeader from "@/components/project/ProjectHeader";
import SealRequestCreateModal from "@/components/project/SealRequestCreateModal";
import SealRequestEditModal from "@/components/project/SealRequestEditModal";
import TaskCreateModal from "@/components/project/TaskCreateModal";
import TaskKanban from "@/components/project/TaskKanban";
import LoadingState from "@/components/ui/LoadingState";
import { cn } from "@/lib/utils";
import useSWR from "swr";

import { deleteSealRequest, getProjectLog, listSealRequests } from "@/lib/api";
import { keys, useCashflow, useProject, useTasks } from "@/lib/hooks";

const SEAL_STATUS_COLOR: Record<string, string> = {
  "1차검토 중": "bg-yellow-500/15 text-yellow-700 dark:text-yellow-400",
  "2차검토 중": "bg-blue-500/15 text-blue-700 dark:text-blue-400",
  반려: "bg-red-500/15 text-red-700 dark:text-red-400",
};

export default function ProjectClient({ id }: { id: string }) {
  const router = useRouter();
  const { mutate } = useSWRConfig();
  const [createOpen, setCreateOpen] = useState(false);
  const [createStatus, setCreateStatus] = useState<string | undefined>(undefined);
  const [editOpen, setEditOpen] = useState(false);
  const [sealOpen, setSealOpen] = useState(false);
  const [sealEditId, setSealEditId] = useState<string | null>(null);
  const [sealBusy, setSealBusy] = useState(false);

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
        <div className="flex items-center gap-2">
          {(() => {
            // seals는 created_time desc로 정렬되어 옴(backend list_seal_requests).
            // 가장 최근 1건의 상태로만 판단 — 과거 반려가 끌려와 새 요청을 막지 않게.
            const latest = seals[0];
            const active =
              latest &&
              (latest.status === "1차검토 중" || latest.status === "2차검토 중")
                ? latest
                : undefined;
            const rejected =
              !active && latest && latest.status === "반려" ? latest : undefined;
            const refreshSeals = (): Promise<unknown> =>
              mutate(["seals", id]);
            const onCancel = async (sid: string): Promise<void> => {
              if (!confirm("날인요청을 취소하시겠습니까?")) return;
              setSealBusy(true);
              try {
                await deleteSealRequest(sid);
                await refreshSeals();
              } catch (e) {
                alert(e instanceof Error ? e.message : "취소 실패");
              } finally {
                setSealBusy(false);
              }
            };
            if (active) {
              return (
                <>
                  <span
                    className={cn(
                      "rounded-md px-2 py-0.5 text-[11px] font-medium",
                      SEAL_STATUS_COLOR[active.status],
                    )}
                  >
                    🔖 {active.status}
                  </span>
                  <button
                    type="button"
                    onClick={() => void onCancel(active.id)}
                    disabled={sealBusy}
                    className="rounded-md border border-red-300 px-2.5 py-1 text-xs text-red-500 hover:bg-red-50 disabled:opacity-50 dark:border-red-900 dark:hover:bg-red-950"
                  >
                    날인취소
                  </button>
                </>
              );
            }
            if (rejected) {
              return (
                <>
                  <span
                    className={cn(
                      "rounded-md px-2 py-0.5 text-[11px] font-medium",
                      SEAL_STATUS_COLOR["반려"],
                    )}
                  >
                    🔖 반려
                  </span>
                  <button
                    type="button"
                    onClick={() => setSealEditId(rejected.id)}
                    className="rounded-md bg-amber-500 px-2.5 py-1 text-xs text-white hover:bg-amber-600"
                  >
                    🔁 날인재요청
                  </button>
                  <button
                    type="button"
                    onClick={() => void onCancel(rejected.id)}
                    disabled={sealBusy}
                    className="rounded-md border border-red-300 px-2.5 py-1 text-xs text-red-500 hover:bg-red-50 disabled:opacity-50 dark:border-red-900 dark:hover:bg-red-950"
                  >
                    날인취소
                  </button>
                </>
              );
            }
            return (
              <button
                type="button"
                onClick={() => setSealOpen(true)}
                className="rounded-md border border-zinc-300 px-2.5 py-1 text-xs hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
              >
                🔖 날인요청
              </button>
            );
          })()}
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
        onCreated={() => {
          setSealOpen(false);
          void mutate(["seals", id]);
        }}
      />

      {sealEditId &&
        (() => {
          const target = seals.find((s) => s.id === sealEditId);
          if (!target) return null;
          return (
            <SealRequestEditModal
              item={target}
              onClose={() => setSealEditId(null)}
              onSaved={() => {
                setSealEditId(null);
                void mutate(["seals", id]);
              }}
            />
          );
        })()}
    </div>
  );
}
