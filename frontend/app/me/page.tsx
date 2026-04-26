"use client";

import Link from "next/link";
import { useState } from "react";
import { useSWRConfig } from "swr";

import { useAuth } from "@/components/AuthGuard";
import ProjectCreateModal from "@/components/me/ProjectCreateModal";
import ProjectImportModal from "@/components/me/ProjectImportModal";
import ProjectTaskRow from "@/components/me/ProjectTaskRow";
import UpcomingDeadlines from "@/components/me/UpcomingDeadlines";
import TaskCreateModal from "@/components/project/TaskCreateModal";
import TaskEditModal from "@/components/project/TaskEditModal";
import LoadingState from "@/components/ui/LoadingState";
import type { Project, ProjectListResponse, Task } from "@/lib/domain";
import { dDayLabel, formatDate } from "@/lib/format";
import { keys, useProjects, useTasks } from "@/lib/hooks";
import { cn } from "@/lib/utils";

export default function MyPage() {
  const { user } = useAuth();
  const { mutate } = useSWRConfig();
  const [editing, setEditing] = useState<Task | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  // 프로젝트별 신규 TASK 모달
  const [taskCreate, setTaskCreate] = useState<{
    projectId: string;
    status?: string;
  } | null>(null);

  const { data: projectData, error: projectErr } = useProjects(
    user?.name ? { mine: true } : undefined,
  );
  const { data: tasksData, error: tasksErr } = useTasks(
    user?.name ? { mine: true } : undefined,
  );

  const error = projectErr ?? tasksErr;
  const tasks = tasksData?.items;
  // mine 프로젝트 = 진행중 + 대기 (완료/타절/종결/이관 제외)
  const candidates = projectData?.items.filter(
    (p) => !p.completed && (p.stage === "진행중" || p.stage === "대기"),
  );
  // 금주 TASK 활동으로 진행중 vs 대기 자동 분류
  const { active: activeProjects, idle: idleProjects } = splitByThisWeek(
    candidates ?? [],
    tasks ?? [],
  );
  // ProjectImportModal / 카운트 등에는 합친 목록 사용
  const projects = candidates;

  const refreshTasks = (): void => {
    void mutate(keys.tasks(user?.name ? { mine: true } : undefined));
  };

  const refreshProjects = (): void => {
    // mine + 전체(import 모달용 stage 필터 캐시) 둘 다 무효화
    void mutate(keys.projects(user?.name ? { mine: true } : undefined));
    void mutate(keys.projects({ stage: "진행중" }));
  };

  /** 본인 담당 해제 시: SWR 캐시에서 그 프로젝트를 즉시 제거 + 백그라운드 revalidate */
  const handleUnassigned = (projectId: string): void => {
    if (!user?.name) return;
    void mutate<ProjectListResponse>(
      keys.projects({ mine: true }),
      (old) =>
        old
          ? {
              ...old,
              items: old.items.filter((p) => p.id !== projectId),
              count: Math.max(0, old.count - 1),
            }
          : old,
      { revalidate: true },
    );
    // import 모달의 "본인 미담당 진행중" 캐시도 새로고침 필요
    void mutate(keys.projects({ stage: "진행중" }));
  };

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
          {user.name} 님이 담당자로 지정된 진행중 프로젝트와 업무 TASK 입니다.
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
          <TodayTasks tasks={tasks} onClickTask={setEditing} />
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
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
            담당 프로젝트 ({projects?.length ?? "—"})
            <span className="ml-2 text-[11px] font-normal text-zinc-500">
              · 금주 TASK 활동으로 진행중/대기 자동 분류
            </span>
          </h2>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setImportOpen(true)}
              className="rounded-md border border-zinc-300 px-2.5 py-1 text-xs hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
            >
              + 프로젝트 가져오기
            </button>
            <button
              type="button"
              onClick={() => setCreateOpen(true)}
              className="rounded-md bg-zinc-900 px-2.5 py-1 text-xs text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
            >
              + 새 프로젝트
            </button>
          </div>
        </div>
        {projects == null ? (
          <LoadingState message="담당 프로젝트 불러오는 중" height="h-32" />
        ) : projects.length === 0 ? (
          <p className="rounded-md border border-zinc-200 bg-white p-4 text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900">
            담당 프로젝트가 없습니다.
          </p>
        ) : (
          <div className="space-y-6">
            {/* 진행중 (금주 TASK 있음) */}
            <div>
              <h3 className="mb-2 flex items-center gap-2 text-xs font-semibold text-blue-600 dark:text-blue-400">
                <span className="h-2 w-2 rounded-full bg-blue-500" />
                진행 중 ({activeProjects.length})
                <span className="text-[10px] font-normal text-zinc-500">
                  금주 활동 있음
                </span>
              </h3>
              {activeProjects.length === 0 ? (
                <p className="rounded-md border border-zinc-200 bg-white p-3 text-xs text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900">
                  금주 활동 중인 프로젝트가 없습니다.
                </p>
              ) : (
                <div className="space-y-4">
                  {activeProjects.map((p) => (
                    <ProjectTaskRow
                      key={p.id}
                      project={p}
                      tasks={(tasks ?? []).filter((t) => taskBelongsTo(t, p.id))}
                      myName={user.name}
                      effectiveActive={true}
                      onChanged={refreshTasks}
                      onCreate={(projectId, status) =>
                        setTaskCreate({ projectId, status })
                      }
                      onUnassigned={handleUnassigned}
                    />
                  ))}
                </div>
              )}
            </div>

            {/* 대기 (금주 TASK 없음) */}
            <div>
              <h3 className="mb-2 flex items-center gap-2 text-xs font-semibold text-purple-600 dark:text-purple-400">
                <span className="h-2 w-2 rounded-full bg-purple-500" />
                대기 ({idleProjects.length})
                <span className="text-[10px] font-normal text-zinc-500">
                  금주 활동 없음
                </span>
              </h3>
              {idleProjects.length === 0 ? (
                <p className="rounded-md border border-zinc-200 bg-white p-3 text-xs text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900">
                  대기 중인 프로젝트가 없습니다.
                </p>
              ) : (
                <div className="space-y-4">
                  {idleProjects.map((p) => (
                    <ProjectTaskRow
                      key={p.id}
                      project={p}
                      tasks={(tasks ?? []).filter((t) => taskBelongsTo(t, p.id))}
                      myName={user.name}
                      effectiveActive={false}
                      onChanged={refreshTasks}
                      onCreate={(projectId, status) =>
                        setTaskCreate({ projectId, status })
                      }
                      onUnassigned={handleUnassigned}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </section>

      <TaskEditModal
        task={editing}
        onClose={() => setEditing(null)}
        onSaved={refreshTasks}
      />

      <ProjectImportModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onAssigned={refreshProjects}
        myName={user.name}
      />

      <ProjectCreateModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={refreshProjects}
      />

      <TaskCreateModal
        open={!!taskCreate}
        projectId={taskCreate?.projectId ?? ""}
        initialStatus={taskCreate?.status}
        onClose={() => setTaskCreate(null)}
        onCreated={refreshTasks}
      />
    </div>
  );
}

function TodayTasks({
  tasks,
  onClickTask,
}: {
  tasks: Task[];
  onClickTask: (t: Task) => void;
}) {
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
      {top.map((t) => (
        <li key={t.id} className="flex items-stretch">
          <button
            type="button"
            onClick={() => onClickTask(t)}
            className="min-w-0 flex-1 px-4 py-2.5 text-left hover:bg-zinc-50 dark:hover:bg-zinc-800/50"
          >
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium" title={t.title}>
                  {t.title || "(제목 없음)"}
                </p>
                <p className="mt-0.5 text-[11px] text-zinc-500">
                  {t.status} · 마감 {formatDate(t.end_date)}
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
          </button>
          {t.project_ids[0] && (
            <Link
              href={`/project?id=${t.project_ids[0]}`}
              className="flex shrink-0 items-center px-3 text-[10px] text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800"
              title="프로젝트로 이동"
            >
              →
            </Link>
          )}
        </li>
      ))}
    </ul>
  );
}

// 노션 page ID 는 응답에 따라 dash 유무가 섞여 있을 수 있어 비교 시 정규화 필요.
function normId(s: string): string {
  return s.replace(/-/g, "").toLowerCase();
}

function taskBelongsTo(t: Task, projectId: string): boolean {
  const target = normId(projectId);
  return t.project_ids.some((pid) => normId(pid) === target);
}

// 이번주 월요일 00:00 ~ 일요일 23:59 범위
function thisWeekRange(): [Date, Date] {
  const now = new Date();
  const day = now.getDay(); // 일=0, 월=1, ..., 토=6
  const offsetToMon = day === 0 ? -6 : 1 - day;
  const mon = new Date(now);
  mon.setDate(now.getDate() + offsetToMon);
  mon.setHours(0, 0, 0, 0);
  const sun = new Date(mon);
  sun.setDate(mon.getDate() + 6);
  sun.setHours(23, 59, 59, 999);
  return [mon, sun];
}

function taskInWeek(t: Task, weekStart: Date, weekEnd: Date): boolean {
  // 기간(start_date~end_date) 또는 actual_end_date 가 금주와 겹치면 true.
  // 양쪽 다 비어있으면 created_time 기반 보조 판정 (있으면).
  const candidates: Array<[string | null, string | null]> = [
    [t.start_date, t.end_date],
  ];
  if (t.actual_end_date) candidates.push([t.actual_end_date, t.actual_end_date]);
  for (const [s, e] of candidates) {
    if (!s && !e) continue;
    const start = s ? new Date(s) : new Date(e!);
    const end = e ? new Date(e) : start;
    end.setHours(23, 59, 59, 999);
    if (start <= weekEnd && end >= weekStart) return true;
  }
  return false;
}

function splitByThisWeek(
  projects: Project[],
  tasks: Task[],
): { active: Project[]; idle: Project[] } {
  const [weekStart, weekEnd] = thisWeekRange();
  const active: Project[] = [];
  const idle: Project[] = [];
  for (const p of projects) {
    const projTasks = tasks.filter((t) => taskBelongsTo(t, p.id));
    const hasThisWeek = projTasks.some((t) => taskInWeek(t, weekStart, weekEnd));
    if (hasThisWeek) active.push(p);
    else idle.push(p);
  }
  return { active, idle };
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
