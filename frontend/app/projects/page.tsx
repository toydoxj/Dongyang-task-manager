"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";

import { useAuth } from "@/components/AuthGuard";
import ProjectCard, {
  type ProjectTag,
} from "@/components/projects/ProjectCard";
import ProjectFilter, {
  type FilterState,
} from "@/components/projects/ProjectFilter";
import ProjectPresets, {
  PRESETS,
  type PresetKey,
} from "@/components/projects/ProjectPresets";
import ProjectTable from "@/components/projects/ProjectTable";
import LoadingState from "@/components/ui/LoadingState";
import { getEmployeeTeamsMap } from "@/lib/api";
import { useProjects, useSealRequests } from "@/lib/hooks";
import type { Project } from "@/lib/domain";

const PAGE_SIZE = 60;
const STALE_DAYS = 90;
// COMMON-002 — list ↔ 상세 왕복 시 필터/스크롤 보존 (탭 단위 저장).
const SS_KEY = "projects-page-state-v1";

interface SavedState {
  filter?: FilterState;
  sortKey?: SortKey;
  view?: "cards" | "table";
  activePreset?: PresetKey | null;
  visibleCount?: number;
  scrollY?: number;
}

function loadSavedState(): SavedState {
  if (typeof window === "undefined") return {};
  const raw = window.sessionStorage.getItem(SS_KEY);
  if (!raw) return {};
  try {
    return JSON.parse(raw) as SavedState;
  } catch {
    return {};
  }
}
const DUE_SOON_DAYS = 30;
const RECENT_EDIT_DAYS = 7;
const INCOME_ISSUE_RATIO = 0.3;
const PENDING_SEAL_STATUSES = new Set(["1차검토 중", "2차검토 중"]);

type SortKey = "start_desc" | "start_asc" | "name_asc" | "amount_desc";

function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function startOfWeekMonday(d: Date): Date {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  const day = x.getDay() || 7;
  x.setDate(x.getDate() - (day - 1));
  return x;
}

function isValidPreset(s: string | null): s is PresetKey {
  return !!s && PRESETS.some((p) => p.key === s);
}

/** 활성 프리셋이 통과하는 프로젝트인지 판정. seals/myTeam은 외부 데이터 의존. */
function projectMatchesPreset(
  p: Project,
  preset: PresetKey,
  ctx: {
    todayStr: string;
    weekStartStr: string;
    weekEndStr: string;
    dueSoonEndStr: string;
    staleCutoffStr: string;
    recentEditCutoffStr: string;
    sealActiveProjectIds: Set<string>;
    myTeam: string | null;
  },
): boolean {
  switch (preset) {
    case "inProgress":
      return p.stage === "진행중";
    case "thisWeekStart":
      return (
        p.start_date != null &&
        p.start_date.slice(0, 10) >= ctx.weekStartStr &&
        p.start_date.slice(0, 10) < ctx.weekEndStr
      );
    case "dueSoon":
      return (
        p.stage === "진행중" &&
        p.contract_end != null &&
        p.contract_end.slice(0, 10) >= ctx.todayStr &&
        p.contract_end.slice(0, 10) <= ctx.dueSoonEndStr
      );
    case "stalled":
      return (
        (p.stage === "진행중" || p.stage === "대기") &&
        p.start_date != null &&
        p.start_date.slice(0, 10) <= ctx.staleCutoffStr
      );
    case "myTeam":
      return ctx.myTeam != null && p.teams.includes(ctx.myTeam);
    case "sealActive":
      return ctx.sealActiveProjectIds.has(p.id);
    case "incomeIssue":
      // 계약 체결 + 용역비 대비 수금 < 30%
      if (!p.contract_signed) return false;
      if (p.contract_amount == null || p.contract_amount <= 0) return false;
      return (
        (p.collection_total ?? 0) < p.contract_amount * INCOME_ISSUE_RATIO
      );
    case "recentEdit":
      return (
        p.last_edited_time != null &&
        p.last_edited_time.slice(0, 10) >= ctx.recentEditCutoffStr
      );
  }
}

/** 시작일 내림차순 비교 (null은 항상 뒤로). */
function cmpDateDesc(a: string | null, b: string | null): number {
  if (!a && !b) return 0;
  if (!a) return 1;
  if (!b) return -1;
  return b.localeCompare(a);
}

export default function ProjectsPage() {
  const { user } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  // admin과 manager만 프로젝트 목록 접근 가능 (사용자 결정 2026-05-11)
  // — team_lead/일반직원은 /me로 redirect
  const allowed = user?.role === "admin" || user?.role === "manager";
  useEffect(() => {
    if (user && !allowed) router.replace("/me");
  }, [user, allowed, router]);

  const { data, error } = useProjects(undefined, allowed);
  const all = data?.items;
  // 직원 명부의 assignee.team 으로 프로젝트 팀을 자동 집계 (노션 '담당팀' 누락 보완).
  const { data: teamsMap } = useSWR(
    ["employee-teams-map"],
    () => getEmployeeTeamsMap(),
  );
  // 날인 진행중 preset 판정용
  const { data: sealData } = useSealRequests(undefined, allowed);

  // URL ?preset 우선, 없으면 sessionStorage. 모든 state는 lazy init으로 sessionStorage 1회 read.
  const presetFromUrl = searchParams.get("preset");
  const presetFromUrlValid =
    presetFromUrl != null && isValidPreset(presetFromUrl);

  const [activePreset, setActivePreset] = useState<PresetKey | null>(() =>
    presetFromUrlValid
      ? (presetFromUrl as PresetKey)
      : (loadSavedState().activePreset ?? null),
  );
  const [filter, setFilter] = useState<FilterState>(
    () =>
      loadSavedState().filter ?? {
        query: "",
        stage: "",
        team: "",
        completed: "open",
      },
  );
  const [sortKey, setSortKey] = useState<SortKey>(
    () => loadSavedState().sortKey ?? "start_desc",
  );
  const [visibleCount, setVisibleCount] = useState(
    () => loadSavedState().visibleCount ?? PAGE_SIZE,
  );
  const [view, setView] = useState<"cards" | "table">(
    () => loadSavedState().view ?? "cards",
  );

  const updateFilter = (next: FilterState) => {
    setFilter(next);
    setVisibleCount(PAGE_SIZE);
  };

  // state 변경 시 sessionStorage 저장 (scrollY는 별도 scroll listener로 갱신).
  useEffect(() => {
    if (typeof window === "undefined") return;
    const next: SavedState = {
      ...loadSavedState(),
      filter,
      sortKey,
      view,
      activePreset,
      visibleCount,
    };
    window.sessionStorage.setItem(SS_KEY, JSON.stringify(next));
  }, [filter, sortKey, view, activePreset, visibleCount]);

  // 데이터 로드 후 1회 scroll restore (back navigation 대응).
  const scrollRestoredRef = useRef(false);
  useEffect(() => {
    if (scrollRestoredRef.current || !all) return;
    const y = loadSavedState().scrollY;
    if (typeof y === "number" && y > 0) {
      requestAnimationFrame(() => window.scrollTo(0, y));
    }
    scrollRestoredRef.current = true;
  }, [all]);

  // scroll 위치를 200ms debounce로 sessionStorage에 저장.
  useEffect(() => {
    if (typeof window === "undefined") return;
    let timer: number | undefined;
    const onScroll = (): void => {
      if (timer) window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        const next: SavedState = {
          ...loadSavedState(),
          scrollY: window.scrollY,
        };
        window.sessionStorage.setItem(SS_KEY, JSON.stringify(next));
      }, 200);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      if (timer) window.clearTimeout(timer);
    };
  }, []);

  const updatePreset = (next: PresetKey | null): void => {
    setActivePreset(next);
    setVisibleCount(PAGE_SIZE);
    // URL 동기화 (스크롤 보존)
    const params = new URLSearchParams(searchParams.toString());
    if (next) params.set("preset", next);
    else params.delete("preset");
    const qs = params.toString();
    router.replace(qs ? `/projects?${qs}` : "/projects", { scroll: false });
  };

  // preset 평가 컨텍스트 (날짜 cutoff + sealActive id set + myTeam)
  const presetCtx = useMemo(() => {
    const today = new Date();
    const todayStr = ymd(today);
    const weekStart = startOfWeekMonday(today);
    const weekEnd = new Date(weekStart);
    weekEnd.setDate(weekEnd.getDate() + 7);
    const dueSoonEnd = new Date(today);
    dueSoonEnd.setDate(dueSoonEnd.getDate() + DUE_SOON_DAYS);
    const staleCutoff = new Date(today);
    staleCutoff.setDate(staleCutoff.getDate() - STALE_DAYS);
    const recentEditCutoff = new Date(today);
    recentEditCutoff.setDate(recentEditCutoff.getDate() - RECENT_EDIT_DAYS);

    const sealActiveProjectIds = new Set<string>();
    for (const s of sealData?.items ?? []) {
      if (!PENDING_SEAL_STATUSES.has(s.status)) continue;
      for (const pid of s.project_ids) sealActiveProjectIds.add(pid);
    }

    // 본인 팀 — 직원 명부 lookup (user.name 기준).
    const myTeam =
      user?.name && teamsMap?.[user.name] ? teamsMap[user.name] : null;

    return {
      todayStr,
      weekStartStr: ymd(weekStart),
      weekEndStr: ymd(weekEnd),
      dueSoonEndStr: ymd(dueSoonEnd),
      staleCutoffStr: ymd(staleCutoff),
      recentEditCutoffStr: ymd(recentEditCutoff),
      sealActiveProjectIds,
      myTeam,
    };
  }, [sealData, teamsMap, user]);

  const filtered = useMemo(() => {
    if (!all) return [];
    const map = teamsMap ?? {};
    const matchesTeam = (
      p: { assignees: string[]; teams: string[] },
      team: string,
    ): boolean => {
      // 직원 명부 우선, 매핑이 없으면 노션 컬럼으로 fallback
      const derived = new Set<string>();
      for (const a of p.assignees) {
        const t = map[a];
        if (t) derived.add(t);
      }
      if (derived.size > 0) return derived.has(team);
      return p.teams.includes(team);
    };
    const q = filter.query.trim().toLowerCase();
    const result = all.filter((p) => {
      if (filter.completed === "open" && p.completed) return false;
      if (filter.completed === "done" && !p.completed) return false;
      if (filter.stage && p.stage !== filter.stage) return false;
      if (filter.team && !matchesTeam(p, filter.team)) return false;
      if (q) {
        const hay = `${p.code} ${p.name}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      if (activePreset && !projectMatchesPreset(p, activePreset, presetCtx)) {
        return false;
      }
      return true;
    });
    // 정렬
    const sorted = [...result];
    sorted.sort((a, b) => {
      switch (sortKey) {
        case "start_desc":
          return cmpDateDesc(a.start_date, b.start_date);
        case "start_asc":
          return -cmpDateDesc(a.start_date, b.start_date);
        case "name_asc":
          return (a.name ?? "").localeCompare(b.name ?? "", "ko");
        case "amount_desc":
          return (b.contract_amount ?? 0) - (a.contract_amount ?? 0);
      }
    });
    return sorted;
  }, [all, filter, sortKey, teamsMap, activePreset, presetCtx]);

  // PROJ-002 — 각 프로젝트의 상태 태그 (cards/table 둘 다 공유)
  const tagsById = useMemo(() => {
    const m = new Map<string, ProjectTag[]>();
    if (!all) return m;
    const closedStages = new Set(["완료", "타절", "종결", "이관"]);
    for (const p of all) {
      const tags: ProjectTag[] = [];
      if (projectMatchesPreset(p, "stalled", presetCtx)) tags.push("stalled");
      if (projectMatchesPreset(p, "dueSoon", presetCtx)) tags.push("dueSoon");
      if (projectMatchesPreset(p, "sealActive", presetCtx))
        tags.push("sealActive");
      if (projectMatchesPreset(p, "incomeIssue", presetCtx))
        tags.push("incomeIssue");
      if (p.assignees.length === 0 && !closedStages.has(p.stage)) {
        tags.push("noAssignee");
      }
      if (projectMatchesPreset(p, "recentEdit", presetCtx))
        tags.push("recentEdit");
      m.set(p.id, tags);
    }
    return m;
  }, [all, presetCtx]);

  // 각 preset을 적용했을 때의 결과 수 — chip count 표시용
  const presetCounts = useMemo(() => {
    if (!all) return undefined;
    const out: Partial<Record<PresetKey, number>> = {};
    // 다른 필터(검색·완료 여부 등)와 무관하게 전체 프로젝트 대비 prelim count
    for (const p of PRESETS) {
      out[p.key] = all.filter((proj) =>
        projectMatchesPreset(proj, p.key, presetCtx),
      ).length;
    }
    return out;
  }, [all, presetCtx]);

  if (!user || !allowed) return null;

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">프로젝트</h1>
        <p className="mt-1 text-sm text-zinc-500">
          담당팀·단계·완료 여부로 필터링하고 카드를 클릭해 상세를 확인하세요.
        </p>
      </header>

      {error && (
        <div className="rounded-md border border-red-500/40 bg-red-500/5 p-3 text-sm text-red-400">
          {error instanceof Error ? error.message : String(error)}
        </div>
      )}

      {all && (
        <>
          <ProjectPresets
            activeKey={activePreset}
            onChange={updatePreset}
            counts={presetCounts}
          />
          <ProjectFilter
            value={filter}
            onChange={updateFilter}
            totalCount={all.length}
            filteredCount={filtered.length}
          />
          <div className="flex flex-wrap items-center gap-3 text-xs">
            <div className="flex items-center gap-2">
              <span className="text-zinc-500">정렬</span>
              <select
                value={sortKey}
                onChange={(e) => {
                  setSortKey(e.target.value as SortKey);
                  setVisibleCount(PAGE_SIZE);
                }}
                className="rounded-md border border-zinc-300 bg-white px-2.5 py-1 outline-none dark:border-zinc-700 dark:bg-zinc-950"
              >
                <option value="start_desc">최신 시작일 (내림차순)</option>
                <option value="start_asc">오래된 시작일 (오름차순)</option>
                <option value="name_asc">이름 (가나다)</option>
                <option value="amount_desc">용역비 (큰 금액 순)</option>
              </select>
            </div>
            <div className="flex items-center gap-1 rounded-md border border-zinc-300 p-0.5 dark:border-zinc-700">
              <button
                type="button"
                onClick={() => setView("cards")}
                className={
                  view === "cards"
                    ? "rounded bg-zinc-900 px-2 py-0.5 text-white dark:bg-zinc-100 dark:text-zinc-900"
                    : "rounded px-2 py-0.5 text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
                }
              >
                카드
              </button>
              <button
                type="button"
                onClick={() => setView("table")}
                className={
                  view === "table"
                    ? "rounded bg-zinc-900 px-2 py-0.5 text-white dark:bg-zinc-100 dark:text-zinc-900"
                    : "rounded px-2 py-0.5 text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
                }
              >
                테이블
              </button>
            </div>
          </div>
        </>
      )}

      {!all && !error && (
        <LoadingState
          message="프로젝트 목록 불러오는 중"
          height="h-64"
        />
      )}

      {all && (
        <>
          {view === "cards" ? (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
              {filtered.slice(0, visibleCount).map((p) => (
                <ProjectCard
                  key={p.id}
                  project={p}
                  tags={tagsById.get(p.id) ?? []}
                />
              ))}
            </div>
          ) : (
            <ProjectTable
              projects={filtered.slice(0, visibleCount)}
              tagsById={tagsById}
            />
          )}

          {filtered.length === 0 && view === "cards" && (
            <p className="py-12 text-center text-sm text-zinc-500">
              조건에 맞는 프로젝트가 없습니다.
            </p>
          )}

          {visibleCount < filtered.length && (
            <div className="flex justify-center pt-2">
              <button
                type="button"
                onClick={() => setVisibleCount((n) => n + PAGE_SIZE)}
                className="rounded-md border border-zinc-300 px-4 py-2 text-sm hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
              >
                더 보기 ({filtered.length - visibleCount}건 남음)
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
