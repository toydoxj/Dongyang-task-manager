"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import useSWR, { useSWRConfig } from "swr";

import { useAuth } from "@/components/AuthGuard";
import MySalesSection from "@/components/me/MySalesSection";
import MyWorkSummaryCards from "@/components/me/MyWorkSummaryCards";
import TasksByTimeView from "@/components/me/TasksByTimeView";
import ProjectCreateModal from "@/components/me/ProjectCreateModal";
import OtherTasksKanban from "@/components/me/OtherTasksKanban";
import ProjectImportModal from "@/components/me/ProjectImportModal";
import ProjectTaskRow from "@/components/me/ProjectTaskRow";
import TaskCreateModal from "@/components/project/TaskCreateModal";
import TaskEditModal from "@/components/project/TaskEditModal";
import LoadingState from "@/components/ui/LoadingState";
import {
  archiveTask,
  getEmployeeTeamsMap,
  listEmployees,
  updateTask,
} from "@/lib/api";
import type { ProjectListResponse, Task } from "@/lib/domain";
import { keys, useProjects, useSealRequests, useTasks } from "@/lib/hooks";

import TodayTasks from "./_TodayTasks";
import { filterCompletedByCutoff, splitByThisWeek } from "./_utils";

// PR-T — 5탭 navigation key/label 상수.
// PR-FF (사용자 요청, 2026-05-17): 순서 재배치 — 담당 프로젝트가 default 진입점.
type TabKey = "projects" | "sales" | "other" | "schedule" | "todo";

const TABS: { key: TabKey; label: string }[] = [
  { key: "projects", label: "담당 프로젝트" },
  { key: "sales", label: "내 영업" },
  { key: "other", label: "기타 업무" },
  { key: "schedule", label: "일정" },
  { key: "todo", label: "할 일" },
];

export default function MyPage() {
  const { user } = useAuth();
  const router = useRouter();
  const sp = useSearchParams();
  // ?as=직원이름 으로 다른 직원 업무 보기 (admin/team_lead 만)
  const overrideName = sp.get("as");
  const isViewingOther = !!overrideName && overrideName !== user?.name;
  const allowedToView =
    !isViewingOther || user?.role === "admin" || user?.role === "team_lead";
  const effectiveName = isViewingOther ? overrideName : user?.name;
  // MY-005 — 팀장(team_lead)·관리자(admin)는 헤더에서 본인/팀원 토글 가능.
  const canSwitchView =
    user?.role === "admin" || user?.role === "team_lead";

  const { mutate } = useSWRConfig();
  const [editing, setEditing] = useState<Task | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  // 프로젝트/영업별 신규 TASK 모달
  const [taskCreate, setTaskCreate] = useState<{
    projectId: string;
    /** 영업별 task 생성 시 — 분류 자동 '영업(서비스)'. */
    saleId?: string;
    status?: string;
    /** 분류 prefill (휴가 카드 + 버튼 등). */
    category?: string;
  } | null>(null);
  // MY-002 — 분류(category) 기준 vs 시간(timeline) 기준 view 토글. default category.
  const [todoViewMode, setTodoViewMode] = useState<"category" | "time">(
    "category",
  );
  const [projectExpandTaskItemsSignal, setProjectExpandTaskItemsSignal] =
    useState(0);
  // PR-T — 5탭 구분 (할일 / 일정 / 담당프로젝트 / 내영업 / 기타업무).
  // URL `?tab=` 우선, 없으면 default "todo".
  const tabFromUrl = sp.get("tab");
  const isValidTab = (s: string | null): s is TabKey =>
    s === "todo" ||
    s === "schedule" ||
    s === "projects" ||
    s === "sales" ||
    s === "other";
  const [activeTab, setActiveTab] = useState<TabKey>(
    isValidTab(tabFromUrl) ? tabFromUrl : "projects",
  );
  const onChangeTab = (next: TabKey): void => {
    setActiveTab(next);
    const params = new URLSearchParams(sp.toString());
    params.set("tab", next);
    router.replace(`/me?${params.toString()}`, { scroll: false });
  };

  // 다른 직원 보기 모드면 mine 대신 assignee=name 으로 fetch
  const fetchFilters = useMemo(
    () =>
      effectiveName
        ? isViewingOther
          ? { assignee: effectiveName }
          : { mine: true }
        : undefined,
    [effectiveName, isViewingOther],
  );

  const { data: projectData, error: projectErr } = useProjects(fetchFilters);
  const { data: tasksData, error: tasksErr } = useTasks(fetchFilters);
  // MY-001 카드 — 본인 검토자(lead/admin) 매칭에 사용. backend는 status 필터 없음 → 전체 fetch.
  const { data: sealData } = useSealRequests();
  // MY-005 — 팀장/관리자가 토글로 팀원 진입 시 사용할 직원 list (admin/team_lead만 fetch).
  const { data: empListData } = useSWR(
    canSwitchView ? ["employees-active"] : null,
    () => listEmployees(undefined, "active"),
  );
  const { data: empTeamsMap } = useSWR(
    canSwitchView ? ["employee-teams-map"] : null,
    () => getEmployeeTeamsMap(),
  );

  // team_lead는 본인 팀 직원만, admin은 전체.
  // 정렬 순서는 /operations/employee-work 와 동일: 팀 → sort_order → 직급 → 이름.
  const switchTargets = useMemo<string[]>(() => {
    if (!canSwitchView || !empListData) return [];
    const TEAM_ORDER = [
      "본부",
      "구조1팀",
      "구조2팀",
      "구조3팀",
      "구조4팀",
      "진단팀",
      "관리팀",
    ];
    const POSITION_ORDER = [
      "사장",
      "부사장",
      "전무",
      "상무",
      "이사",
      "실장",
      "차장",
      "과장",
      "대리",
      "기사",
      "사원",
    ];
    const orderOf = (arr: readonly string[], v: string): number => {
      const i = arr.indexOf(v);
      return i === -1 ? arr.length : i;
    };
    const myTeam = user?.name ? empTeamsMap?.[user.name] : undefined;
    const filtered = empListData.items.filter((e) => {
      if (!e.name || e.name === user?.name) return false;
      if (user?.role === "admin") return true;
      if (!myTeam) return false;
      return empTeamsMap?.[e.name] === myTeam;
    });
    filtered.sort((a, b) => {
      const t =
        orderOf(TEAM_ORDER, a.team ?? "") - orderOf(TEAM_ORDER, b.team ?? "");
      if (t !== 0) return t;
      const s = (a.sort_order ?? 0) - (b.sort_order ?? 0);
      if (s !== 0) return s;
      const p =
        orderOf(POSITION_ORDER, a.position ?? "") -
        orderOf(POSITION_ORDER, b.position ?? "");
      if (p !== 0) return p;
      return a.name.localeCompare(b.name, "ko");
    });
    return filtered.map((e) => e.name);
  }, [canSwitchView, empListData, empTeamsMap, user]);

  const onSwitchView = (target: string): void => {
    if (target === "__self__" || target === user?.name) {
      router.push("/me");
    } else {
      router.push(`/me?as=${encodeURIComponent(target)}`);
    }
  };

  const error = projectErr ?? tasksErr;
  const allTasks = tasksData?.items;
  // 내 업무 정책: 완료된 TASK는 이번주 월요일 -14일 이후만 표시.
  // PR-FI/9: 4탭 모두 동일 cutoff — _utils.filterCompletedByCutoff helper 사용.
  const tasks = useMemo<Task[] | undefined>(
    () => (allTasks ? filterCompletedByCutoff(allTasks) : allTasks),
    [allTasks],
  );
  // mine 프로젝트 = 진행중 + 대기 (완료/타절/종결/이관 제외)
  const candidates = useMemo(
    () =>
      projectData?.items.filter(
        (p) => !p.completed && (p.stage === "진행중" || p.stage === "대기"),
      ),
    [projectData?.items],
  );
  // 금주 TASK 활동으로 진행중 vs 대기 자동 분류
  const { active: activeProjects, idle: idleProjects } = useMemo(
    () => splitByThisWeek(candidates ?? [], tasks ?? []),
    [candidates, tasks],
  );
  // ProjectImportModal / 카운트 등에는 합친 목록 사용
  const projects = candidates;

  const refreshTasks = (): void => {
    // mine tasks + 프로젝트별 tasks(다른 직원 담당분) 캐시 모두 무효화 — task 편집 후
    // ProjectTaskRow 의 자체 fetch 와 페이지의 mine fetch 둘 다 갱신되도록.
    void mutate(
      (key) => Array.isArray(key) && key[0] === "tasks",
      undefined,
      { revalidate: true },
    );
  };

  const handleDeleteTask = async (t: Task): Promise<void> => {
    if (!confirm(`"${t.title || "(제목 없음)"}" 업무를 삭제하시겠습니까?\n보관 처리됩니다.`)) {
      return;
    }
    try {
      await archiveTask(t.id);
      refreshTasks();
    } catch (e) {
      alert(e instanceof Error ? e.message : "삭제 실패");
    }
  };

  const handleCompleteTask = async (t: Task): Promise<void> => {
    try {
      await updateTask(t.id, { status: "완료" });
      refreshTasks();
    } catch (e) {
      alert(e instanceof Error ? e.message : "완료 처리 실패");
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
          직원 명부와 일치하는 이름으로 프로필을 설정해주세요.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">
            {isViewingOther ? `${effectiveName} 님의 업무` : "내 업무"}
          </h1>
          <p className="mt-1 text-sm text-zinc-500">
            {isViewingOther ? (
              <>
                {effectiveName} 님이 담당자로 지정된 진행중 프로젝트와 업무 TASK
                입니다.
              </>
            ) : (
              `${effectiveName} 님이 담당자로 지정된 진행중 프로젝트와 업무 TASK 입니다.`
            )}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {canSwitchView && switchTargets.length > 0 && (
            <select
              value={isViewingOther ? (effectiveName ?? "") : "__self__"}
              onChange={(e) => onSwitchView(e.target.value)}
              className="rounded-md border border-zinc-300 bg-white px-2.5 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
              title={
                user?.role === "team_lead"
                  ? "본인 팀 직원의 업무로 전환"
                  : "직원 업무 전환"
              }
            >
              <option value="__self__">내 업무</option>
              <optgroup
                label={user?.role === "team_lead" ? "팀원" : "전체 직원"}
              >
                {switchTargets.map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </optgroup>
            </select>
          )}
          <Link
            href="/weekly-report"
            className="rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-700"
          >
            주간업무일지 보기
          </Link>
        </div>
      </header>

      {error && (
        <div className="rounded-md border border-red-500/40 bg-red-500/5 p-3 text-sm text-red-400">
          {error instanceof Error ? error.message : String(error)}
        </div>
      )}

      <MyWorkSummaryCards
        myName={effectiveName}
        projects={projects ?? []}
        tasks={tasks ?? []}
        sealRequests={sealData?.items ?? []}
      />

      {/* PR-T — 5탭 navigation (PR-FF: 순서 재배치) */}
      <nav
        aria-label="섹션 전환"
        className="flex flex-wrap items-center gap-1 border-b border-zinc-200 dark:border-zinc-800"
      >
        {TABS.map((t) => {
          const isActive = activeTab === t.key;
          return (
            <button
              key={t.key}
              type="button"
              onClick={() => onChangeTab(t.key)}
              className={
                isActive
                  ? "-mb-px border-b-2 border-zinc-900 px-3 py-1.5 text-sm font-semibold text-zinc-900 dark:border-zinc-100 dark:text-zinc-100"
                  : "px-3 py-1.5 text-sm font-medium text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
              }
            >
              {t.label}
            </button>
          );
        })}
      </nav>

      {activeTab === "todo" && (
        <section className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
          <div className="mb-3 flex items-center justify-end gap-2">
            <div className="flex items-center gap-1 rounded-md border border-zinc-300 p-0.5 text-[11px] dark:border-zinc-700">
              <button
                type="button"
                onClick={() => setTodoViewMode("category")}
                className={
                  todoViewMode === "category"
                    ? "rounded bg-zinc-900 px-2 py-0.5 text-white dark:bg-zinc-100 dark:text-zinc-900"
                    : "rounded px-2 py-0.5 text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
                }
              >
                분류
              </button>
              <button
                type="button"
                onClick={() => setTodoViewMode("time")}
                className={
                  todoViewMode === "time"
                    ? "rounded bg-zinc-900 px-2 py-0.5 text-white dark:bg-zinc-100 dark:text-zinc-900"
                    : "rounded px-2 py-0.5 text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
                }
              >
                시간
              </button>
            </div>
          </div>
          {tasks == null ? (
            <LoadingState message="내 업무 TASK 불러오는 중" height="h-32" />
          ) : todoViewMode === "time" ? (
            <TasksByTimeView
              tasks={tasks}
              projects={projects ?? []}
              onClickTask={setEditing}
              onDeleteTask={handleDeleteTask}
              onCompleteTask={handleCompleteTask}
            />
          ) : (
            <TodayTasks
              tasks={tasks}
              projects={projects ?? []}
              onClickTask={setEditing}
              onDeleteTask={handleDeleteTask}
              scope="todo"
            />
          )}
        </section>
      )}

      {activeTab === "schedule" && (
        <section className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
          {tasks == null ? (
            <LoadingState message="일정 불러오는 중" height="h-32" />
          ) : (
            <TodayTasks
              tasks={tasks}
              projects={projects ?? []}
              onClickTask={setEditing}
              onDeleteTask={handleDeleteTask}
              onAddVacation={() =>
                setTaskCreate({ projectId: "", category: "휴가(연차)" })
              }
              scope="schedule"
            />
          )}
        </section>
      )}

      {activeTab === "projects" && (
      <section>
        <div className="mb-2 flex items-center justify-between gap-2">
          <h2 className="flex items-center gap-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
            담당 프로젝트 ({projects?.length ?? "—"})
          </h2>
          <div className="flex flex-wrap justify-end gap-2">
            <button
              type="button"
              onClick={() => setProjectExpandTaskItemsSignal((v) => v + 1)}
              disabled={(projects?.length ?? 0) === 0}
              className="rounded-md border border-zinc-300 px-2.5 py-1 text-xs hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
            >
              TASK 있는 항목 펼치기
            </button>
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
                      myName={effectiveName}
                      forUser={isViewingOther ? effectiveName ?? undefined : undefined}
                      effectiveActive={true}
                      onChanged={refreshTasks}
                      onCreate={(projectId, status) =>
                        setTaskCreate({ projectId, status })
                      }
                      onUnassigned={handleUnassigned}
                      expandTaskItemsSignal={projectExpandTaskItemsSignal}
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
                      myName={effectiveName}
                      forUser={isViewingOther ? effectiveName ?? undefined : undefined}
                      effectiveActive={false}
                      onChanged={refreshTasks}
                      onCreate={(projectId, status) =>
                        setTaskCreate({ projectId, status })
                      }
                      onUnassigned={handleUnassigned}
                      expandTaskItemsSignal={projectExpandTaskItemsSignal}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </section>
      )}

      {activeTab === "sales" && (
        <MySalesSection
          effectiveName={effectiveName}
          isViewingOther={isViewingOther}
          onCreateTask={(saleId, status) =>
            setTaskCreate({
              projectId: "",
              saleId,
              status,
              category: "영업(서비스)",
            })
          }
        />
      )}

      {activeTab === "other" && (
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
              [
                "개인업무",
                "사내잡무",
                "교육",
                "서비스",
                "영업(서비스)",
              ].includes(t.category),
            )}
            onClickTask={setEditing}
            onDeleteTask={handleDeleteTask}
            onChanged={refreshTasks}
          />
        )}
      </section>
      )}

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
        saleId={taskCreate?.saleId}
        projects={projects ?? []}
        defaultAssignee={effectiveName}
        initialStatus={taskCreate?.status}
        initialCategory={taskCreate?.category}
        onClose={() => setTaskCreate(null)}
        onCreated={refreshTasks}
      />
    </div>
  );
}
/** 일정용: ISO datetime이면 'MM/DD HH:mm', 아니면 'YYYY.MM.DD' */
