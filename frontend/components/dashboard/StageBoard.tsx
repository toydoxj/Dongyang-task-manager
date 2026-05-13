"use client";

import {
  DndContext,
  DragEndEvent,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { useMemo, useState } from "react";
import useSWR, { mutate as globalMutate } from "swr";

import { useAuth } from "@/components/AuthGuard";
import {
  ClosedStackColumn,
  type CloseMode,
  CreateColumn,
  StageColumn,
} from "@/components/dashboard/StageBoardColumns";
import ProjectCreateModal from "@/components/me/ProjectCreateModal";
import ProjectStageChangeModal from "@/components/project/ProjectStageChangeModal";
import { getEmployeeTeamsMap, setProjectStage } from "@/lib/api";
import type { Project, ProjectListResponse } from "@/lib/domain";
import { PROJECT_STAGES, TEAMS } from "@/lib/domain";
import { keys } from "@/lib/hooks";
import { cn } from "@/lib/utils";

interface Props {
  projects: Project[];
}

const CLOSE_MODES: ReadonlySet<string> = new Set<CloseMode>([
  "완료",
  "타절",
  "종결",
]);
// 한 컬럼 안에 세로 stack으로 묶어 보여주는 종료성 단계들 (보드 가로 폭 축소 목적)
const STACKED_CLOSED: ReadonlyArray<CloseMode> = ["완료", "타절", "종결"];

export default function StageBoard({ projects }: Props) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [items, setItems] = useState<Project[]>(projects);
  const [err, setErr] = useState<string | null>(null);
  const [activeTeam, setActiveTeam] = useState<string>("전체");
  // 드래그로 완료/타절/종결 컬럼에 떨어뜨렸을 때 띄우는 모달 상태
  const [pendingClose, setPendingClose] = useState<{
    project: Project;
    mode: CloseMode;
  } | null>(null);
  // 보드 우측 끝 [+ 새 프로젝트] 모달
  const [createOpen, setCreateOpen] = useState(false);

  // 부모가 새 데이터 주면 동기화 (SWR revalidate)
  if (projects !== items && projects.length !== items.length) {
    setItems(projects);
  }

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
  );

  // 노션 '담당팀' 컬럼은 갱신이 누락되는 경우가 많아 직원 명부의
  // assignee.team 으로 프로젝트 팀을 자동 집계 (ProjectHeader와 동일 패턴).
  // teams-map 이 비어있는 동안에는 노션 p.teams 를 fallback 으로 사용.
  const { data: teamsMap } = useSWR(
    ["employee-teams-map"],
    () => getEmployeeTeamsMap(),
  );
  const projectTeams = useMemo((): Map<string, Set<string>> => {
    const map = teamsMap ?? {};
    const out = new Map<string, Set<string>>();
    for (const p of items) {
      const teams = new Set<string>();
      for (const a of p.assignees) {
        const t = map[a];
        if (t) teams.add(t);
      }
      // 담당자가 매핑되지 않는 경우(전 직원/외부) 노션 컬럼으로 보조
      if (teams.size === 0) {
        for (const t of p.teams) teams.add(t);
      }
      out.set(p.id, teams);
    }
    return out;
  }, [items, teamsMap]);

  // 팀별 카운트 (탭 라벨용)
  const teamCount = new Map<string, number>();
  teamCount.set("전체", items.length);
  for (const team of TEAMS) {
    teamCount.set(
      team,
      items.filter((p) => projectTeams.get(p.id)?.has(team)).length,
    );
  }

  // 활성 탭 기준 필터
  const filteredItems =
    activeTeam === "전체"
      ? items
      : items.filter((p) => projectTeams.get(p.id)?.has(activeTeam));

  // 완료/타절/종결 그룹은 완료일이 최근 2주(14일) 이내인 것만 표시
  const TWO_WEEKS_AGO_ISO = (() => {
    const d = new Date();
    d.setDate(d.getDate() - 14);
    return d.toISOString().slice(0, 10);
  })();
  const isRecentlyClosed = (p: Project): boolean => {
    if (!p.end_date) return false;
    return p.end_date.slice(0, 10) >= TWO_WEEKS_AGO_ISO;
  };
  const CLOSED_STAGES = new Set(["완료", "타절", "종결"]);

  const grouped = new Map<string, Project[]>();
  for (const stage of PROJECT_STAGES) grouped.set(stage, []);
  for (const p of filteredItems) {
    const list = grouped.get(p.stage);
    if (!list) continue;
    if (CLOSED_STAGES.has(p.stage) && !isRecentlyClosed(p)) continue;
    list.push(p);
  }

  async function handleDragEnd(e: DragEndEvent): Promise<void> {
    const { active, over } = e;
    if (!over) return;
    if (!isAdmin) {
      setErr("진행단계 변경은 관리자만 가능합니다.");
      return;
    }
    const projectId = String(active.id);
    const targetStage = String(over.id);
    const proj = items.find((p) => p.id === projectId);
    if (!proj || proj.stage === targetStage) return;
    if (targetStage === "진행중") {
      setErr("'진행중'은 금주 TASK 활동으로 자동 결정됩니다. 수동 변경 불가.");
      return;
    }

    setErr(null);

    // 완료/타절/종결은 완료일·금액 등 부수 정보가 필요해 모달로 위임.
    // optimistic update 안 하므로 모달 취소 시 카드는 자연스럽게 원위치.
    if (CLOSE_MODES.has(targetStage)) {
      setPendingClose({ project: proj, mode: targetStage as CloseMode });
      return;
    }

    // 대기/보류/이관: 즉시 stage만 변경
    const prev = items;
    setItems(items.map((p) => (p.id === projectId ? { ...p, stage: targetStage } : p)));

    try {
      await setProjectStage(projectId, targetStage);
      // SWR 캐시도 갱신
      void globalMutate(
        keys.projects(),
        (old: ProjectListResponse | undefined) =>
          old
            ? {
                ...old,
                items: old.items.map((p) =>
                  p.id === projectId ? { ...p, stage: targetStage } : p,
                ),
              }
            : old,
        { revalidate: true },
      );
    } catch (e) {
      // rollback
      setItems(prev);
      setErr(e instanceof Error ? e.message : "단계 변경 실패");
    }
  }

  const tabs = ["전체", ...TEAMS];

  return (
    <div className="min-w-0 space-y-2">
      {/* 팀별 필터 탭 */}
      <div className="flex flex-wrap gap-1 border-b border-zinc-200 dark:border-zinc-800">
        {tabs.map((t) => {
          const count = teamCount.get(t) ?? 0;
          const active = activeTeam === t;
          return (
            <button
              key={t}
              type="button"
              onClick={() => setActiveTeam(t)}
              className={cn(
                "border-b-2 px-3 py-1.5 text-xs transition-colors",
                active
                  ? "border-blue-500 text-blue-600 dark:text-blue-400"
                  : "border-transparent text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300",
              )}
            >
              {t} <span className="ml-1 text-zinc-400">({count})</span>
            </button>
          );
        })}
      </div>

      {!isAdmin && (
        <p className="rounded-md border border-zinc-300 bg-zinc-50 p-2 text-xs text-zinc-600 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-400">
          진행단계 변경은 관리자만 가능합니다. 카드 드래그는 비활성화되어 있습니다.
        </p>
      )}
      {err && (
        <p className="rounded-md border border-amber-500/40 bg-amber-500/5 p-2 text-xs text-amber-500">
          {err}
        </p>
      )}
      <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
        <div className="flex gap-3 overflow-x-auto pb-2">
          {PROJECT_STAGES.map((stage) => {
            // 완료 등장 시 종료성 stack 컬럼 한 번 렌더, 타절/종결은 skip
            if (stage === STACKED_CLOSED[0]) {
              return (
                <ClosedStackColumn
                  key="closed-stack"
                  sections={STACKED_CLOSED.map((s) => ({
                    stage: s,
                    items: grouped.get(s) ?? [],
                  }))}
                  draggable={isAdmin}
                />
              );
            }
            if (STACKED_CLOSED.slice(1).includes(stage as CloseMode)) {
              return null;
            }
            return (
              <StageColumn
                key={stage}
                stage={stage}
                items={grouped.get(stage) ?? []}
                draggable={isAdmin}
              />
            );
          })}
          <CreateColumn onClick={() => setCreateOpen(true)} />
        </div>
      </DndContext>

      {pendingClose && (
        <ProjectStageChangeModal
          project={pendingClose.project}
          defaultMode={pendingClose.mode}
          onClose={() => setPendingClose(null)}
          onSaved={() => {
            const id = pendingClose.project.id;
            const newStage = pendingClose.mode;
            setItems((prev) =>
              prev.map((p) =>
                p.id === id ? { ...p, stage: newStage } : p,
              ),
            );
            void globalMutate(
              keys.projects(),
              (old: ProjectListResponse | undefined) =>
                old
                  ? {
                      ...old,
                      items: old.items.map((p) =>
                        p.id === id ? { ...p, stage: newStage } : p,
                      ),
                    }
                  : old,
              { revalidate: true },
            );
            setPendingClose(null);
          }}
        />
      )}

      <ProjectCreateModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={() => {
          // 보드 데이터는 부모(SWR)에서 갱신 — 캐시만 invalidate
          void globalMutate(keys.projects());
        }}
        emptyAssignees
      />
    </div>
  );
}

