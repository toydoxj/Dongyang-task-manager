"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { useSWRConfig } from "swr";

import { useAuth } from "@/components/AuthGuard";
import ProjectCreateModal from "@/components/me/ProjectCreateModal";
import OtherTasksKanban from "@/components/me/OtherTasksKanban";
import ProjectImportModal from "@/components/me/ProjectImportModal";
import ProjectTaskRow from "@/components/me/ProjectTaskRow";
import TaskCreateModal from "@/components/project/TaskCreateModal";
import TaskEditModal from "@/components/project/TaskEditModal";
import LoadingState from "@/components/ui/LoadingState";
import { archiveTask } from "@/lib/api";
import type { Project, ProjectListResponse, Task } from "@/lib/domain";
import { dDayLabel, formatDate } from "@/lib/format";
import { keys, useProjects, useTasks } from "@/lib/hooks";
import { cn } from "@/lib/utils";

export default function MyPage() {
  const { user } = useAuth();
  const sp = useSearchParams();
  // ?as=직원이름 으로 다른 직원 업무 보기 (admin/team_lead 만)
  const overrideName = sp.get("as");
  const isViewingOther = !!overrideName && overrideName !== user?.name;
  const allowedToView =
    !isViewingOther || user?.role === "admin" || user?.role === "team_lead";
  const effectiveName = isViewingOther ? overrideName : user?.name;

  const { mutate } = useSWRConfig();
  const [editing, setEditing] = useState<Task | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  // 프로젝트별 신규 TASK 모달
  const [taskCreate, setTaskCreate] = useState<{
    projectId: string;
    status?: string;
  } | null>(null);
  // '해야할 일' 섹션 접기 (사용자가 자주 보는 영역이라 default 펼침)
  const [todoCollapsed, setTodoCollapsed] = useState(false);
  // '담당 프로젝트' 섹션 접기 — default 펼침
  const [projectsCollapsed, setProjectsCollapsed] = useState(false);

  // 다른 직원 보기 모드면 mine 대신 assignee=name 으로 fetch
  const fetchFilters = effectiveName
    ? isViewingOther
      ? { assignee: effectiveName }
      : { mine: true }
    : undefined;

  const { data: projectData, error: projectErr } = useProjects(fetchFilters);
  const { data: tasksData, error: tasksErr } = useTasks(fetchFilters);

  const error = projectErr ?? tasksErr;
  const allTasks = tasksData?.items;
  // 내 업무 정책: 완료된 TASK는 '완료된지 주 기준 저저번 주 이전' 까지만 표시.
  // cutoff = (이번주 월요일 00:00 KST) - 14일. 그보다 오래된 완료 task는 숨김.
  const tasks = useMemo<Task[] | undefined>(() => {
    if (!allTasks) return allTasks;
    const now = new Date();
    const dow = now.getDay(); // 0=Sun, 1=Mon..6=Sat
    const diffToMon = dow === 0 ? -6 : 1 - dow;
    const monday = new Date(now);
    monday.setDate(monday.getDate() + diffToMon);
    monday.setHours(0, 0, 0, 0);
    monday.setDate(monday.getDate() - 14);
    const cutoffMs = monday.getTime();
    return allTasks.filter((t) => {
      if (t.status !== "완료") return true;
      const ref = t.actual_end_date ?? t.last_edited_time;
      if (!ref) return true; // 시점 모르면 안전하게 보여줌
      return new Date(ref).getTime() >= cutoffMs;
    });
  }, [allTasks]);
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
    void mutate(keys.tasks(fetchFilters));
  };

  const handleDeleteTask = async (t: Task): Promise<void> => {
    if (!confirm(`"${t.title || "(제목 없음)"}" 업무를 삭제하시겠습니까?\n노션에서 보관 처리됩니다.`)) {
      return;
    }
    try {
      await archiveTask(t.id);
      refreshTasks();
    } catch (e) {
      alert(e instanceof Error ? e.message : "삭제 실패");
    }
  };

  const refreshProjects = (): void => {
    // 모든 projects cache 무효화 — 다른 곳에서 변경된 상태(예: TaskEditModal에서
    // 프로젝트 담당 추가)도 즉시 반영. SWR이 자동 revalidate.
    void mutate(
      (key) => Array.isArray(key) && key[0] === "projects",
      undefined,
      { revalidate: true },
    );
  };

  /** 본인 담당 해제 시: 현재 list에서 즉시 제거 + 다른 캐시는 invalidate만 */
  const handleUnassigned = (projectId: string): void => {
    if (!effectiveName) return;
    // (1) 현재 list에서 optimistic 제거. revalidate=false — backend 재호출이
    //     stale 응답을 돌려보내 그 프로젝트가 다시 나타나는 race를 방지.
    //     unassignMe 호출이 mirror upsert까지 마치고 응답하므로 backend는
    //     최신 상태이지만, SWR의 dedupingInterval/inflight 충돌 가능.
    void mutate<ProjectListResponse>(
      keys.projects(fetchFilters),
      (old) =>
        old
          ? {
              ...old,
              items: old.items.filter((p) => p.id !== projectId),
              count: Math.max(0, old.count - 1),
            }
          : old,
      { revalidate: false },
    );
    // (2) 다른 페이지 캐시는 invalidate만 — 다른 페이지 진입 시 자동 fetch
    void mutate(
      (key) =>
        Array.isArray(key) &&
        key[0] === "projects" &&
        JSON.stringify(key[1]) !== JSON.stringify(fetchFilters ?? null),
      undefined,
      { revalidate: false },
    );
  };

  if (isViewingOther && !allowedToView) {
    return (
      <div className="space-y-3">
        <h1 className="text-2xl font-semibold">권한 없음</h1>
        <p className="rounded-md border border-red-500/40 bg-red-500/5 p-3 text-sm text-red-400">
          다른 직원의 업무는 관리자/팀장만 조회할 수 있습니다.
        </p>
      </div>
    );
  }

  if (!effectiveName) {
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
        <h1 className="text-2xl font-semibold">
          {isViewingOther ? `${effectiveName} 님의 업무` : "내 업무"}
        </h1>
        <p className="mt-1 text-sm text-zinc-500">
          {isViewingOther ? (
            <>
              {effectiveName} 님이 담당자로 지정된 진행중 프로젝트와 업무 TASK
              입니다. <Link href="/admin/employee-work" className="underline">
                ← 직원 변경
              </Link>
            </>
          ) : (
            `${effectiveName} 님이 담당자로 지정된 진행중 프로젝트와 업무 TASK 입니다.`
          )}
        </p>
      </header>

      {error && (
        <div className="rounded-md border border-red-500/40 bg-red-500/5 p-3 text-sm text-red-400">
          {error instanceof Error ? error.message : String(error)}
        </div>
      )}

      <section className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
        <button
          type="button"
          onClick={() => setTodoCollapsed((v) => !v)}
          className="flex w-full items-center justify-between gap-2 text-left"
          aria-expanded={!todoCollapsed}
        >
          <h2 className="flex items-center gap-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
            <span className="text-zinc-400">{todoCollapsed ? "▶" : "▼"}</span>
            해야할 일
          </h2>
          <span className="text-[10px] text-zinc-500">
            {todoCollapsed ? "펼치기" : "접기"}
          </span>
        </button>
        {!todoCollapsed && (
          <div className="mt-3">
            {tasks == null ? (
              <LoadingState message="내 업무 TASK 불러오는 중" height="h-32" />
            ) : (
              <TodayTasks
                tasks={tasks}
                projects={projects ?? []}
                onClickTask={setEditing}
                onDeleteTask={handleDeleteTask}
              />
            )}
          </div>
        )}
      </section>

      <hr className="border-zinc-200 dark:border-zinc-800" />

      <section>
        <div className="mb-2 flex items-center justify-between gap-2">
          <button
            type="button"
            onClick={() => setProjectsCollapsed((v) => !v)}
            className="flex items-center gap-2 text-left text-sm font-medium text-zinc-700 hover:text-zinc-900 dark:text-zinc-300 dark:hover:text-zinc-100"
            aria-expanded={!projectsCollapsed}
          >
            <span className="text-zinc-400">
              {projectsCollapsed ? "▶" : "▼"}
            </span>
            담당 프로젝트 ({projects?.length ?? "—"})
            <span className="ml-1 text-[10px] font-normal text-zinc-500">
              {projectsCollapsed ? "펼치기" : "접기"}
            </span>
          </button>
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
        {projectsCollapsed ? null : projects == null ? (
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
                      myName={effectiveName}
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
                      myName={effectiveName}
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

      <hr className="border-zinc-200 dark:border-zinc-800" />

      <section>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
            기타 업무 (프로젝트 외)
          </h2>
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-zinc-500">
              카드를 끌어 상태 변경 · ✕ 로 삭제
            </span>
            <button
              type="button"
              onClick={() => setTaskCreate({ projectId: "" })}
              className="rounded-md bg-zinc-900 px-2.5 py-1 text-xs text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
            >
              + 새 업무
            </button>
          </div>
        </div>
        {tasks == null ? (
          <LoadingState message="불러오는 중" height="h-32" />
        ) : (
          <OtherTasksKanban
            tasks={tasks.filter((t) =>
              ["개인업무", "사내잡무", "교육", "서비스"].includes(t.category),
            )}
            onClickTask={setEditing}
            onDeleteTask={handleDeleteTask}
            onChanged={refreshTasks}
          />
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
        myName={effectiveName}
        forUser={isViewingOther ? effectiveName : undefined}
      />

      <ProjectCreateModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={refreshProjects}
        forUser={isViewingOther ? effectiveName : undefined}
      />

      <TaskCreateModal
        open={!!taskCreate}
        projectId={taskCreate?.projectId ?? ""}
        projects={projects ?? []}
        defaultAssignee={effectiveName}
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
  onDeleteTask,
}: {
  tasks: Task[];
  projects: Project[];
  onClickTask: (t: Task) => void;
  onDeleteTask: (t: Task) => void;
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
  // 2) 미분류 → amber 영역
  // 3) 기타 업무(개인업무/사내잡무/교육/서비스) → status별 4열 카드
  // 4) 일정 → 3열 카드 (분류=외근/출장/휴가 OR 활동=외근/출장 인 task 모두)
  //    - 프로젝트 task가 활동=외근이면 일정에도 함께 노출
  const NON_PROJECT_WORK = ["개인업무", "사내잡무", "교육", "서비스"];
  const STATUSES = ["시작 전", "진행 중", "완료", "보류"] as const;

  const projectTasks: Task[] = [];
  const otherByStatus = new Map<string, Task[]>();
  for (const s of STATUSES) otherByStatus.set(s, []);
  const scheduleByBucket = new Map<string, Task[]>([
    ["외근", []],
    ["출장", []],
    ["휴가", []],
  ]);
  const unclassified: Task[] = [];

  // 휴가는 옛 표기('휴가')와 새 표기('휴가(연차)') 모두 같은 일정 버킷으로 처리
  const isVacationCat = (c: string): boolean => c === "휴가" || c === "휴가(연차)";

  for (const t of open) {
    // 일정 영역에 등장해야 하는가 (분류 또는 활동 기준)
    const scheduleBucket =
      isVacationCat(t.category)
        ? "휴가"
        : t.activity === "출장" || t.category === "출장"
          ? "출장"
          : t.activity === "외근" || t.category === "외근"
            ? "외근"
            : null;
    if (scheduleBucket) {
      scheduleByBucket.get(scheduleBucket)!.push(t);
    }

    // 메인 그룹 (프로젝트/기타/미분류) — 일정 분류는 메인에서 제외, 단 프로젝트 분류는 일정과 별개로 메인에 둠
    if (t.category === "프로젝트") {
      projectTasks.push(t);
    } else if (NON_PROJECT_WORK.includes(t.category)) {
      const bucket = otherByStatus.get(t.status) ?? otherByStatus.get("시작 전")!;
      bucket.push(t);
    } else if (
      t.category === "외근" ||
      t.category === "출장" ||
      isVacationCat(t.category)
    ) {
      // 일정 분류 task는 메인 영역에 추가 안 함 (일정 카드에만 표시)
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
          onDeleteTask={onDeleteTask}
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
                onDelete={() => onDeleteTask(t)}
                warn
              />
            ))}
          </ul>
        </div>
      )}

      {/* 일정 — 외근/출장/휴가 3열 카드 (시간 표시). 분류=일정 OR 활동=일정 모두. */}
      <div>
        <h3 className="mb-1.5 text-xs font-medium text-zinc-600 dark:text-zinc-400">
          일정
        </h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {(["외근", "출장", "휴가"] as const).map((c) => (
            <CategoryCard
              key={c}
              label={c}
              items={scheduleByBucket.get(c) ?? []}
              onClickTask={onClickTask}
              showTime
              showProjectBadge
              findProject={findProject}
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
  onDeleteTask,
}: {
  items: Task[];
  findProject: (pid: string | undefined) => Project | undefined;
  onClickTask: (t: Task) => void;
  onDeleteTask: (t: Task) => void;
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
            onDelete={() => onDeleteTask(t)}
          />
        ))}
      </ul>
    </div>
  );
}

function ActivityBadge({ activity }: { activity?: string }) {
  if (!activity || activity === "사무실") return null;
  const cls =
    activity === "외근"
      ? "bg-orange-500/15 text-orange-600 dark:text-orange-400"
      : activity === "출장"
        ? "bg-red-500/15 text-red-600 dark:text-red-400"
        : "bg-zinc-500/15 text-zinc-500";
  return (
    <span className={cn("rounded px-1 py-0.5 text-[9px] font-medium", cls)}>
      {activity}
    </span>
  );
}

function TaskCard({
  task: t,
  project: proj,
  onClick,
  onDelete,
  warn,
}: {
  task: Task;
  project?: Project;
  onClick: () => void;
  onDelete?: () => void;
  warn?: boolean;
}) {
  return (
    <li
      className={cn(
        "group relative flex items-stretch overflow-hidden rounded-lg border bg-white dark:bg-zinc-900",
        warn
          ? "border-amber-300/60 dark:border-amber-700/60"
          : "border-zinc-200 dark:border-zinc-800",
      )}
    >
      {onDelete && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          className="absolute right-1 top-1 z-10 hidden rounded p-0.5 text-zinc-400 hover:bg-red-500/15 hover:text-red-500 group-hover:block"
          title="삭제"
        >
          ×
        </button>
      )}
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
          <div className="flex shrink-0 flex-col items-end gap-1">
            <span
              className={cn(
                "rounded-md px-2 py-0.5 text-[10px] font-medium",
                statusBadgeColor(t),
              )}
            >
              {dDayLabel(t.end_date) || "—"}
            </span>
            <ActivityBadge activity={t.activity} />
          </div>
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
  showProjectBadge,
  findProject,
}: {
  label: string;
  items: Task[];
  onClickTask: (t: Task) => void;
  showCategoryBadge?: boolean;
  showTime?: boolean;
  showProjectBadge?: boolean;
  findProject?: (pid: string | undefined) => Project | undefined;
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
                {showProjectBadge && t.category === "프로젝트" && findProject && (
                  <p className="mt-0.5 truncate text-[10px] text-zinc-500">
                    {(() => {
                      const proj = findProject(t.project_ids[0]);
                      return proj ? `${proj.code || ""} ${proj.name}` : "프로젝트";
                    })()}
                  </p>
                )}
                <p className="mt-0.5 flex items-center justify-between gap-1 text-[10px] text-zinc-500">
                  <span className="truncate">
                    {showTime
                      ? formatRange(t.start_date, t.end_date)
                      : `마감 ${formatDate(t.end_date)}`}
                  </span>
                  <span className="flex shrink-0 items-center gap-1">
                    <ActivityBadge activity={t.activity} />
                    {showCategoryBadge && t.category && (
                      <span className="rounded bg-zinc-100 px-1 py-0.5 text-[9px] text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                        {t.category}
                      </span>
                    )}
                    {!showCategoryBadge && (
                      <span
                        className={cn(
                          "rounded px-1 py-0.5 text-[9px] font-medium",
                          statusBadgeColor(t),
                        )}
                      >
                        {dDayLabel(t.end_date) || "—"}
                      </span>
                    )}
                  </span>
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
