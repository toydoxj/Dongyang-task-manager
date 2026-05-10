"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useSWRConfig } from "swr";

import AssigneeTimeline from "@/components/project/AssigneeTimeline";
import LifecycleTimeline from "@/components/project/LifecycleTimeline";
import ProjectCashflowChart from "@/components/project/ProjectCashflowChart";
import ProjectEditModal from "@/components/project/ProjectEditModal";
import ProjectHeader from "@/components/project/ProjectHeader";
import SealRequestCreateModal from "@/components/project/SealRequestCreateModal";
import SealRequestDetailModal from "@/components/project/SealRequestDetailModal";
import SealRequestEditModal from "@/components/project/SealRequestEditModal";
import TaskCreateModal from "@/components/project/TaskCreateModal";
import TaskKanban from "@/components/project/TaskKanban";
import LoadingState from "@/components/ui/LoadingState";
import { cn } from "@/lib/utils";
import useSWR from "swr";

import {
  deleteSealRequest,
  findSaleByProject,
  getProjectLog,
  listSealRequests,
} from "@/lib/api";
import { keys, useCashflow, useProject, useTasks } from "@/lib/hooks";

const SEAL_STATUS_COLOR: Record<string, string> = {
  "1차검토 중": "bg-yellow-500/15 text-yellow-700 dark:text-yellow-400",
  "2차검토 중": "bg-blue-500/15 text-blue-700 dark:text-blue-400",
  반려: "bg-red-500/15 text-red-700 dark:text-red-400",
};

/** 뒤로 가기 버튼 — render 외부 정의 (rules-of-hooks/static-components). */
function BackButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="text-xs text-zinc-500 hover:underline"
    >
      ← 뒤로
    </button>
  );
}

export default function ProjectClient({ id }: { id: string }) {
  const router = useRouter();
  const { mutate } = useSWRConfig();
  const [createOpen, setCreateOpen] = useState(false);
  const [createStatus, setCreateStatus] = useState<string | undefined>(undefined);
  const [editOpen, setEditOpen] = useState(false);
  const [sealOpen, setSealOpen] = useState(false);
  const [sealEditId, setSealEditId] = useState<string | null>(null);
  const [sealBusy, setSealBusy] = useState(false);
  // 날인 현황에서 항목 클릭 시 read-only 상세 모달
  const [sealDetailId, setSealDetailId] = useState<string | null>(null);
  // 재날인요청 — SealRequestCreateModal에 prefill로 사용
  const [sealRedoItem, setSealRedoItem] = useState<
    import("@/lib/api").SealRequestItem | null
  >(null);

  // 어디서 왔든 그 페이지로 돌아가기. history 없으면 /projects로 fallback.
  const goBack = (): void => {
    if (typeof window !== "undefined" && window.history.length > 1) {
      router.back();
    } else {
      router.push("/projects");
    }
  };

  const { data: project, error: projectErr } = useProject(id);
  const { data: tasksData, error: tasksErr } = useTasks({ project_id: id });
  const { data: cashflowData, error: cashflowErr } = useCashflow({
    project_id: id,
  });
  const { data: sealsData } = useSWR(["seals", id], () =>
    listSealRequests({ projectId: id }),
  );
  const seals = sealsData?.items ?? [];
  // 영업 reverse lookup — converted_project_id == id 인 영업 1건
  const { data: linkedSale } = useSWR(["sale-by-project", id], () =>
    findSaleByProject(id),
  );
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
        <BackButton onClick={goBack} />
        <div className="rounded-md border border-red-500/40 bg-red-500/5 p-3 text-sm text-red-400">
          {error instanceof Error ? error.message : String(error)}
        </div>
      </div>
    );
  }

  if (!project || !tasks || !cashflow) {
    return (
      <div className="space-y-4">
        <BackButton onClick={goBack} />
        <LoadingState
          message="프로젝트 상세 불러오는 중"
          height="h-64"
        />
      </div>
    );
  }

  // seals는 created_time desc로 정렬되어 옴(backend list_seal_requests).
  // 가장 최근 1건의 상태로만 판단 — 과거 반려가 끌려와 새 요청을 막지 않게.
  const latest = seals[0];
  const sealActive =
    latest &&
    (latest.status === "1차검토 중" || latest.status === "2차검토 중")
      ? latest
      : undefined;
  const sealRejected =
    !sealActive && latest && latest.status === "반려" ? latest : undefined;

  const onCancelSeal = async (sid: string): Promise<void> => {
    if (!confirm("날인요청을 취소하시겠습니까?")) return;
    setSealBusy(true);
    try {
      await deleteSealRequest(sid);
      // 취소는 연결 TASK도 '완료'로 마감 → 칸반/타임라인까지 같이 갱신
      await mutate(["seals", id]);
      refreshTasks();
    } catch (e) {
      alert(e instanceof Error ? e.message : "취소 실패");
    } finally {
      setSealBusy(false);
    }
  };

  const headerActions = (
    <>
      <button
        type="button"
        onClick={() => setEditOpen(true)}
        className="rounded-md border border-zinc-300 px-2.5 py-1 text-xs hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
      >
        편집
      </button>
      {linkedSale && (
        <button
          type="button"
          onClick={() =>
            router.push(
              `/sales?sale=${encodeURIComponent(linkedSale.id)}&from=${encodeURIComponent(
                `/projects/${id}`,
              )}`,
            )
          }
          className="rounded-md border border-emerald-400 px-2.5 py-1 text-xs text-emerald-700 hover:bg-emerald-50 dark:border-emerald-700 dark:text-emerald-400 dark:hover:bg-emerald-950"
          title={`영업 ${linkedSale.code || ""} ${linkedSale.name} 상세 보기`}
        >
          📋 영업 상세
        </button>
      )}
      {/* 진행 중인 날인 요청 상태 표시 */}
      {sealActive && (
        <>
          <span
            className={cn(
              "rounded-md px-2 py-0.5 text-[11px] font-medium",
              SEAL_STATUS_COLOR[sealActive.status],
            )}
          >
            🔖 {sealActive.status}
          </span>
          <button
            type="button"
            onClick={() => void onCancelSeal(sealActive.id)}
            disabled={sealBusy}
            className="rounded-md border border-red-300 px-2.5 py-1 text-xs text-red-500 hover:bg-red-50 disabled:opacity-50 dark:border-red-900 dark:hover:bg-red-950"
          >
            날인취소
          </button>
        </>
      )}
      {sealRejected && (
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
            onClick={() => setSealEditId(sealRejected.id)}
            className="rounded-md bg-amber-500 px-2.5 py-1 text-xs text-white hover:bg-amber-600"
          >
            🔁 날인재요청
          </button>
          <button
            type="button"
            onClick={() => void onCancelSeal(sealRejected.id)}
            disabled={sealBusy}
            className="rounded-md border border-red-300 px-2.5 py-1 text-xs text-red-500 hover:bg-red-50 disabled:opacity-50 dark:border-red-900 dark:hover:bg-red-950"
          >
            날인취소
          </button>
        </>
      )}
      {/* 날인요청 — 항상 노출 (동일 프로젝트에 N개 가능). 진행 중인 요청이 있어도
          별도 검토 자료(예: 보고서 + 구조계산서)를 추가할 수 있도록 허용. */}
      <button
        type="button"
        onClick={() => setSealOpen(true)}
        className="rounded-md border border-zinc-300 px-2.5 py-1 text-xs hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
      >
        {sealActive || sealRejected ? "+ 날인요청 추가" : "🔖 날인요청"}
      </button>
    </>
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <BackButton onClick={goBack} />
        <div className="flex items-center gap-2">
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

      <ProjectHeader project={project} actions={headerActions} />
      <LifecycleTimeline
        project={project}
        tasks={tasks}
        seals={seals}
        logs={logs}
      />

      <AssigneeTimeline project={project} logs={logs} />

      <div id="seals" className="scroll-mt-4">
        <SealHistoryList
          seals={seals}
          onClick={(s) => setSealDetailId(s.id)}
        />
      </div>

      <div id="tasks" className="scroll-mt-4">
        <TaskKanban tasks={tasks} onChanged={refreshTasks} onCreate={openCreate} />
      </div>

      <div id="cashflow" className="scroll-mt-4">
        <ProjectCashflowChart project={project} entries={cashflow} />
      </div>

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
        open={sealOpen || sealRedoItem !== null}
        fixedProject={project}
        redoFrom={sealRedoItem}
        onClose={() => {
          setSealOpen(false);
          setSealRedoItem(null);
        }}
        onCreated={() => {
          setSealOpen(false);
          setSealRedoItem(null);
          // 재날인요청 시: 노션 page update + 자동 TASK 새 사이클 생성. 화면 전체
          // 새 데이터를 받도록 관련 SWR key를 모두 mutate.
          void mutate(["seals", id]);
          refreshTasks();
          void mutate(keys.project(id));
          void mutate(["project-log", id]);
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
                refreshTasks();
              }}
            />
          );
        })()}

      {sealDetailId &&
        (() => {
          const target = seals.find((s) => s.id === sealDetailId);
          if (!target) return null;
          return (
            <SealRequestDetailModal
              item={target}
              onClose={() => setSealDetailId(null)}
              onRedo={(it) => {
                setSealDetailId(null);
                setSealRedoItem(it);
              }}
            />
          );
        })()}
    </div>
  );
}

const SEAL_HISTORY_BADGE: Record<string, string> = {
  "1차검토 중": "bg-yellow-500/15 text-yellow-700 dark:text-yellow-400",
  "2차검토 중": "bg-blue-500/15 text-blue-700 dark:text-blue-400",
  승인: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
  반려: "bg-red-500/15 text-red-700 dark:text-red-400",
};

function SealHistoryList({
  seals,
  onClick,
}: {
  seals: import("@/lib/api").SealRequestItem[];
  onClick: (s: import("@/lib/api").SealRequestItem) => void;
}) {
  if (seals.length === 0) return null;
  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
      <header className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold">날인 현황 ({seals.length})</h2>
        <p className="text-[11px] text-zinc-500">
          항목 클릭 시 상세 보기 + 재날인요청 가능
        </p>
      </header>
      <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
        {seals.map((s) => {
          const dateLabel = s.requested_at
            ? new Date(s.requested_at).toLocaleDateString("ko-KR", {
                year: "2-digit",
                month: "2-digit",
                day: "2-digit",
              })
            : "—";
          return (
            <li key={s.id}>
              <button
                type="button"
                onClick={() => onClick(s)}
                className="flex w-full items-center gap-3 px-1 py-2 text-left hover:bg-zinc-50 dark:hover:bg-zinc-800/50"
              >
                <span className="w-12 shrink-0 text-[10px] text-zinc-400">
                  {dateLabel}
                </span>
                <span
                  className={cn(
                    "shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-medium",
                    SEAL_HISTORY_BADGE[s.status] ??
                      "bg-zinc-500/15 text-zinc-500",
                  )}
                >
                  {s.status}
                </span>
                <span className="shrink-0 rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
                  {s.seal_type}
                </span>
                <span
                  className="flex-1 truncate text-xs text-zinc-900 dark:text-zinc-100"
                  title={s.title}
                >
                  {s.title || "(제목 없음)"}
                </span>
                {s.doc_no && (
                  <span className="hidden shrink-0 font-mono text-[10px] text-zinc-500 sm:inline">
                    {s.doc_no}
                  </span>
                )}
                <span className="shrink-0 text-[10px] text-zinc-400">
                  {s.requester}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
