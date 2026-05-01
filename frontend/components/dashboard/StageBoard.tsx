"use client";

import {
  DndContext,
  DragEndEvent,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import Link from "next/link";
import { useState } from "react";
import { mutate as globalMutate } from "swr";

import { useAuth } from "@/components/AuthGuard";
import ProjectStageChangeModal from "@/components/project/ProjectStageChangeModal";
import { setProjectStage } from "@/lib/api";
import type { Project, ProjectListResponse } from "@/lib/domain";
import { PROJECT_STAGES, TEAMS } from "@/lib/domain";
import { formatWon } from "@/lib/format";
import { keys } from "@/lib/hooks";
import { cn } from "@/lib/utils";

interface Props {
  projects: Project[];
}

type CloseMode = "완료" | "타절" | "종결";
const CLOSE_MODES: ReadonlySet<string> = new Set<CloseMode>([
  "완료",
  "타절",
  "종결",
]);

const STAGE_COLOR: Record<string, string> = {
  "진행중": "border-blue-500/40 bg-blue-500/5",
  "대기": "border-purple-500/40 bg-purple-500/5",
  "보류": "border-pink-500/40 bg-pink-500/5",
  "완료": "border-emerald-500/40 bg-emerald-500/5",
  "타절": "border-red-500/40 bg-red-500/5",
  "종결": "border-zinc-500/40 bg-zinc-500/5",
  "이관": "border-zinc-400/30 bg-zinc-400/5",
};

const STAGE_DOT: Record<string, string> = {
  "진행중": "bg-blue-500",
  "대기": "bg-purple-500",
  "보류": "bg-pink-500",
  "완료": "bg-emerald-500",
  "타절": "bg-red-500",
  "종결": "bg-zinc-500",
  "이관": "bg-zinc-400",
};

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

  // 부모가 새 데이터 주면 동기화 (SWR revalidate)
  if (projects !== items && projects.length !== items.length) {
    setItems(projects);
  }

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
  );

  // 팀별 카운트 (탭 라벨용) — 미완료 + 그 팀 담당
  const teamCount = new Map<string, number>();
  teamCount.set("전체", items.length);
  for (const team of TEAMS) {
    teamCount.set(team, items.filter((p) => p.teams.includes(team)).length);
  }

  // 활성 탭 기준 필터
  const filteredItems =
    activeTeam === "전체"
      ? items
      : items.filter((p) => p.teams.includes(activeTeam));

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
    <div className="space-y-2">
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
          {PROJECT_STAGES.map((stage) => (
            <StageColumn
              key={stage}
              stage={stage}
              items={grouped.get(stage) ?? []}
              draggable={isAdmin}
            />
          ))}
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
    </div>
  );
}

function StageColumn({
  stage,
  items,
  draggable,
}: {
  stage: string;
  items: Project[];
  draggable: boolean;
}) {
  const isAutoStage = stage === "진행중";
  const { isOver, setNodeRef } = useDroppable({
    id: stage,
    disabled: isAutoStage || !draggable, // 진행중 컬럼/비-admin은 drop 차단
  });
  const total = items.reduce((s, p) => s + (p.contract_amount ?? 0), 0);
  const [expanded, setExpanded] = useState(false);
  const VISIBLE = 50;
  const visibleItems = expanded ? items : items.slice(0, VISIBLE);

  return (
    <div
      ref={setNodeRef}
      className={cn(
        "flex w-72 flex-shrink-0 flex-col rounded-xl border bg-white transition-colors dark:bg-zinc-900",
        STAGE_COLOR[stage] ?? "border-zinc-300",
        isOver && !isAutoStage && "ring-2 ring-blue-400",
        isAutoStage && "opacity-95",
      )}
    >
      <header className="flex items-center justify-between border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
        <div className="flex items-center gap-2">
          <span className={cn("h-2 w-2 rounded-full", STAGE_DOT[stage])} />
          <h3 className="text-sm font-semibold">{stage}</h3>
          <span className="text-xs text-zinc-500">{items.length}건</span>
          {isAutoStage && (
            <span
              className="rounded bg-blue-500/15 px-1 py-0.5 text-[9px] text-blue-500"
              title="금주 TASK 활동으로 자동 결정"
            >
              자동
            </span>
          )}
        </div>
        <span className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
          {formatWon(total, true)}
        </span>
      </header>

      <ul className="max-h-[480px] space-y-1.5 overflow-y-auto p-2">
        {items.length === 0 && (
          <li className="px-2 py-6 text-center text-xs text-zinc-400">
            비어있음
          </li>
        )}
        {visibleItems.map((p) => (
          <ProjectCard key={p.id} project={p} draggable={draggable} />
        ))}
        {items.length > VISIBLE && (
          <li>
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="w-full rounded-md py-1.5 text-center text-[10px] text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-300"
            >
              {expanded
                ? "▲ 접기"
                : `▼ ${items.length - VISIBLE}건 더 보기`}
            </button>
          </li>
        )}
      </ul>
    </div>
  );
}

function ProjectCard({
  project: p,
  draggable,
}: {
  project: Project;
  draggable: boolean;
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } =
    useDraggable({ id: p.id, disabled: !draggable });

  const style: React.CSSProperties | undefined = transform
    ? {
        transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`,
        zIndex: 50,
      }
    : undefined;

  return (
    <li
      ref={setNodeRef}
      style={style}
      className={cn(
        "select-none touch-none",
        isDragging && "opacity-60",
      )}
      {...attributes}
      {...listeners}
    >
      <div className="rounded-md border border-zinc-200 bg-white p-2.5 text-xs transition-colors hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950 dark:hover:bg-zinc-900">
        <div className="flex items-start justify-between gap-1">
          <p
            className="truncate font-medium text-zinc-900 dark:text-zinc-100"
            title={p.name}
          >
            {p.name || "(제목 없음)"}
          </p>
          {/* 카드 자체는 drag 영역. 우측 → 링크는 drag 충돌 방지 위해 PointerEvents 막음 */}
          <Link
            href={`/project?id=${p.id}`}
            onPointerDown={(e) => e.stopPropagation()}
            className="shrink-0 text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200"
            title="상세"
          >
            ↗
          </Link>
        </div>
        <div className="mt-1 flex items-center justify-between">
          <span className="font-mono text-[10px] text-zinc-500">
            {p.code || "—"}
          </span>
          <span className="text-[10px] text-zinc-500">
            {p.assignees.length > 0
              ? p.assignees.length === 1
                ? p.assignees[0]
                : `${p.assignees[0]} +${p.assignees.length - 1}`
              : "—"}
          </span>
        </div>
      </div>
    </li>
  );
}
