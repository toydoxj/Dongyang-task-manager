"use client";

import Link from "next/link";
import { useState } from "react";
import { useSWRConfig } from "swr";

import { useAuth } from "@/components/AuthGuard";
import ProjectCreateModal from "@/components/me/ProjectCreateModal";
import ProjectImportModal from "@/components/me/ProjectImportModal";
import ProjectTaskRow from "@/components/me/ProjectTaskRow";
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
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
            해야할 일
          </h2>
          <button
            type="button"
            onClick={() => setTaskCreate({ projectId: "" })}
            className="rounded-md bg-zinc-900 px-2.5 py-1 text-xs text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
          >
            + 새 업무
          </button>
        </div>
        {tasks == null ? (
          <LoadingState message="내 업무 TASK 불러오는 중" height="h-32" />
        ) : (
          <TodayTasks
            tasks={tasks}
            projects={projects ?? []}
            onClickTask={setEditing}
          />
        )}
      </section>

      <hr className="border-zinc-200 dark:border-zinc-800" />

      <section>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
            담당 프로젝트 ({projects?.length ?? "—"})
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
        projects={projects ?? []}
        initialStatus={taskCreate?.status}
        onClose={() => setTaskCreate(null)}
        onCreated={refreshTasks}
      />
    </div>
  );
}

function TodayTasks({
  tasks,
  projects,
  onClickTask,
}: {
  tasks: Task[];
  projects: Project[];
  onClickTask: (t: Task) => void;
}) {
  const open = tasks.filter((t) => t.status !== "완료");
  open.sort((a, b) => {
    if (!a.end_date && !b.end_date) return 0;
    if (!a.end_date) return 1;
    if (!b.end_date) return -1;
    return a.end_date.localeCompare(b.end_date);
  });

  if (open.length === 0) {
    return (
      <p className="rounded-md border border-zinc-200 bg-white p-4 text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900">
        오늘 처리할 업무가 없습니다. 🎉
      </p>
    );
  }

  // project_id → name lookup (id에 dash 유무 차이 무시)
  const projectByNorm = new Map<string, Project>();
  for (const p of projects) {
    projectByNorm.set(normId(p.id), p);
  }
  const findProject = (pid: string | undefined): Project | undefined =>
    pid ? projectByNorm.get(normId(pid)) : undefined;

  // 1) 프로젝트 분류 → 상단 2열 grid
  // 2) 미분류 → amber 영역 (분류 권장)
  // 3) 기타 업무(개인업무/사내잡무/교육/서비스) → status별 4열 카드
  // 4) 일정(외근/출장/휴가) → 3열 카드 (시간 표시)
  const NON_PROJECT_WORK = ["개인업무", "사내잡무", "교육", "서비스"];
  const SCHEDULE_CATS = ["외근", "출장", "휴가"];
  const STATUSES = ["시작 전", "진행 중", "완료", "보류"] as const;

  const projectTasks: Task[] = [];
  const otherByStatus = new Map<string, Task[]>();
  for (const s of STATUSES) otherByStatus.set(s, []);
  const scheduleByCat = new Map<string, Task[]>();
  for (const c of SCHEDULE_CATS) scheduleByCat.set(c, []);
  const unclassified: Task[] = [];

  for (const t of open) {
    if (t.category === "프로젝트") {
      projectTasks.push(t);
    } else if (NON_PROJECT_WORK.includes(t.category)) {
      const bucket = otherByStatus.get(t.status) ?? otherByStatus.get("시작 전")!;
      bucket.push(t);
    } else if (SCHEDULE_CATS.includes(t.category)) {
      scheduleByCat.get(t.category)!.push(t);
    } else {
      unclassified.push(t);
    }
  }

  return (
    <div className="space-y-5">
      {projectTasks.length > 0 && (
        <ProjectTaskList
          items={projectTasks}
          findProject={findProject}
          onClickTask={onClickTask}
        />
      )}

      {unclassified.length > 0 && (
        <div>
          <h3 className="mb-1.5 flex items-center gap-2 text-xs font-medium text-amber-600 dark:text-amber-400">
            <span>미분류 — 분류를 지정해 주세요</span>
            <span className="text-zinc-400">({unclassified.length})</span>
          </h3>
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {unclassified.map((t) => (
              <TaskCard
                key={t.id}
                task={t}
                project={findProject(t.project_ids[0])}
                onClick={() => onClickTask(t)}
                warn
              />
            ))}
          </ul>
        </div>
      )}

      {/* 기타 업무 — status별 4열 카드 */}
      <div>
        <h3 className="mb-1.5 text-xs font-medium text-zinc-600 dark:text-zinc-400">
          기타 업무 (프로젝트 외)
        </h3>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {STATUSES.map((s) => (
            <CategoryCard
              key={s}
              label={s}
              items={otherByStatus.get(s) ?? []}
              onClickTask={onClickTask}
              showCategoryBadge
            />
          ))}
        </div>
      </div>

      {/* 일정 — 외근/출장/휴가 3열 카드 (시간 표시) */}
      <div>
        <h3 className="mb-1.5 text-xs font-medium text-zinc-600 dark:text-zinc-400">
          일정
        </h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {SCHEDULE_CATS.map((c) => (
            <CategoryCard
              key={c}
              label={c}
              items={scheduleByCat.get(c) ?? []}
              onClickTask={onClickTask}
              showTime
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function ProjectTaskList({
  items,
  findProject,
  onClickTask,
}: {
  items: Task[];
  findProject: (pid: string | undefined) => Project | undefined;
  onClickTask: (t: Task) => void;
}) {
  return (
    <div>
      <h3 className="mb-1.5 flex items-center gap-2 text-xs font-medium text-zinc-600 dark:text-zinc-400">
        <span>프로젝트</span>
        <span className="text-zinc-400">({items.length})</span>
      </h3>
      <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {items.map((t) => (
          <TaskCard
            key={t.id}
            task={t}
            project={findProject(t.project_ids[0])}
            onClick={() => onClickTask(t)}
          />
        ))}
      </ul>
    </div>
  );
}

function TaskCard({
  task: t,
  project: proj,
  onClick,
  warn,
}: {
  task: Task;
  project?: Project;
  onClick: () => void;
  warn?: boolean;
}) {
  return (
    <li
      className={cn(
        "flex items-stretch overflow-hidden rounded-lg border bg-white dark:bg-zinc-900",
        warn
          ? "border-amber-300/60 dark:border-amber-700/60"
          : "border-zinc-200 dark:border-zinc-800",
      )}
    >
      <button
        type="button"
        onClick={onClick}
        className="min-w-0 flex-1 px-3 py-2.5 text-left hover:bg-zinc-50 dark:hover:bg-zinc-800/50"
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium" title={t.title}>
              {t.title || "(제목 없음)"}
            </p>
            {proj && (
              <p
                className="mt-0.5 truncate text-[11px] text-zinc-600 dark:text-zinc-400"
                title={proj.name}
              >
                <span className="font-mono text-zinc-400">
                  {proj.code || proj.id.slice(0, 6)}
                </span>
                <span className="ml-1.5">{proj.name}</span>
              </p>
            )}
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
  );
}

function CategoryCard({
  label,
  items,
  onClickTask,
  showCategoryBadge,
  showTime,
}: {
  label: string;
  items: Task[];
  onClickTask: (t: Task) => void;
  showCategoryBadge?: boolean;
  showTime?: boolean;
}) {
  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900">
      <header className="mb-2 flex items-center justify-between">
        <h4 className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">
          {label}
        </h4>
        <span className="text-[10px] text-zinc-500">{items.length}</span>
      </header>
      {items.length === 0 ? (
        <p className="py-4 text-center text-[11px] text-zinc-400">없음</p>
      ) : (
        <ul className="space-y-1.5">
          {items.map((t) => (
            <li key={t.id}>
              <button
                type="button"
                onClick={() => onClickTask(t)}
                className="block w-full rounded-md border border-zinc-200 bg-white px-2 py-1.5 text-left text-xs hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950 dark:hover:bg-zinc-900"
              >
                <p className="truncate font-medium" title={t.title}>
                  {t.title || "(제목 없음)"}
                </p>
                <p className="mt-0.5 flex items-center justify-between gap-1 text-[10px] text-zinc-500">
                  <span className="truncate">
                    {showTime
                      ? formatRange(t.start_date, t.end_date)
                      : `마감 ${formatDate(t.end_date)}`}
                  </span>
                  {showCategoryBadge && t.category && (
                    <span className="shrink-0 rounded bg-zinc-100 px-1 py-0.5 text-[9px] text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                      {t.category}
                    </span>
                  )}
                  {!showCategoryBadge && (
                    <span
                      className={cn(
                        "shrink-0 rounded px-1 py-0.5 text-[9px] font-medium",
                        statusBadgeColor(t),
                      )}
                    >
                      {dDayLabel(t.end_date) || "—"}
                    </span>
                  )}
                </p>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** 일정용: ISO datetime이면 'MM/DD HH:mm', 아니면 'YYYY.MM.DD' */
function formatRange(start: string | null, end: string | null): string {
  const fmt = (s: string | null): string => {
    if (!s) return "";
    if (s.includes("T")) {
      const d = new Date(s);
      if (Number.isNaN(d.getTime())) return s;
      return new Intl.DateTimeFormat("ko-KR", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
        timeZone: "Asia/Seoul",
      }).format(d);
    }
    return formatDate(s);
  };
  const a = fmt(start);
  const b = fmt(end);
  if (a && b && a === b) return a;
  if (a && b) return `${a} ~ ${b}`;
  return a || b || "—";
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
