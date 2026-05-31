"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";

import { useRoleGuard } from "@/lib/useRoleGuard";
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
import ProjectTable, {
  type ProjectSortDir,
  type ProjectTableSortKey,
} from "@/components/projects/ProjectTable";
import LoadingState from "@/components/ui/LoadingState";
import { getEmployeeTeamsMap } from "@/lib/api";
import { PROJECT_STAGES, type Project } from "@/lib/domain";
import { useProjects, useSealRequests } from "@/lib/hooks";

const PAGE_SIZE = 60;
const STALE_DAYS = 90;
// COMMON-002 — list ↔ 상세 왕복 시 필터/스크롤 보존 (탭 단위 저장).
const SS_KEY = "projects-page-state-v1";

type SortKey = ProjectTableSortKey | "start_date";
type LegacySortKey = "start_desc" | "start_asc" | "name_asc" | "amount_desc";

interface SortState {
  key: SortKey;
  dir: ProjectSortDir;
}

interface SavedState {
  filter?: FilterState;
  sortKey?: SortKey | LegacySortKey | null;
  sortDir?: ProjectSortDir;
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

const TABLE_SORT_KEYS = [
  "code",
  "name",
  "stage",
  "client",
  "team",
  "assignees",
  "contract_period",
  "amount",
  "collection_rate",
] as const satisfies readonly ProjectTableSortKey[];

const SORT_KEYS = [
  "start_date",
  ...TABLE_SORT_KEYS,
] as const satisfies readonly SortKey[];

type SortOptionValue = `${SortKey}:${ProjectSortDir}`;

const SORT_OPTIONS: { value: SortOptionValue; label: string }[] = [
  { value: "start_date:desc", label: "최신 시작일 (내림차순)" },
  { value: "start_date:asc", label: "오래된 시작일 (오름차순)" },
  { value: "code:asc", label: "코드 (오름차순)" },
  { value: "code:desc", label: "코드 (내림차순)" },
  { value: "name:asc", label: "이름 (가나다)" },
  { value: "name:desc", label: "이름 (역순)" },
  { value: "stage:asc", label: "단계 (정방향)" },
  { value: "stage:desc", label: "단계 (역방향)" },
  { value: "client:asc", label: "발주처 (가나다)" },
  { value: "client:desc", label: "발주처 (역순)" },
  { value: "team:asc", label: "담당팀 (가나다)" },
  { value: "team:desc", label: "담당팀 (역순)" },
  { value: "assignees:asc", label: "담당자 (가나다)" },
  { value: "assignees:desc", label: "담당자 (역순)" },
  { value: "contract_period:desc", label: "계약기간 (최신 시작)" },
  { value: "contract_period:asc", label: "계약기간 (오래된 시작)" },
  { value: "amount:desc", label: "용역비 (큰 금액 순)" },
  { value: "amount:asc", label: "용역비 (작은 금액 순)" },
  { value: "collection_rate:desc", label: "수금률 (높은 순)" },
  { value: "collection_rate:asc", label: "수금률 (낮은 순)" },
];

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

function isSortKey(value: unknown): value is SortKey {
  return (
    typeof value === "string" && (SORT_KEYS as readonly string[]).includes(value)
  );
}

function isProjectTableSortKey(value: SortKey): value is ProjectTableSortKey {
  return (TABLE_SORT_KEYS as readonly string[]).includes(value);
}

function isSortDir(value: unknown): value is ProjectSortDir {
  return value === "asc" || value === "desc";
}

function defaultSortDir(key: SortKey): ProjectSortDir {
  switch (key) {
    case "start_date":
    case "contract_period":
    case "amount":
    case "collection_rate":
      return "desc";
    case "code":
    case "name":
    case "stage":
    case "client":
    case "team":
    case "assignees":
      return "asc";
  }
}

function loadSavedSort(): SortState {
  const saved = loadSavedState();
  switch (saved.sortKey) {
    case "start_desc":
      return { key: "start_date", dir: "desc" };
    case "start_asc":
      return { key: "start_date", dir: "asc" };
    case "name_asc":
      return { key: "name", dir: "asc" };
    case "amount_desc":
      return { key: "amount", dir: "desc" };
  }

  if (isSortKey(saved.sortKey)) {
    return {
      key: saved.sortKey,
      dir: isSortDir(saved.sortDir)
        ? saved.sortDir
        : defaultSortDir(saved.sortKey),
    };
  }

  return { key: "start_date", dir: "desc" };
}

function parseSortOptionValue(value: string): SortState {
  const [key, dir] = value.split(":");
  if (isSortKey(key) && isSortDir(dir)) return { key, dir };
  return { key: "start_date", dir: "desc" };
}

function sortOptionValue(sort: SortState): SortOptionValue {
  return `${sort.key}:${sort.dir}` as SortOptionValue;
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

const koCollator = new Intl.Collator("ko", {
  numeric: true,
  sensitivity: "base",
});

function compareText(a: string, b: string, dir: number): number {
  const av = a.trim();
  const bv = b.trim();
  if (!av && !bv) return 0;
  if (!av) return 1;
  if (!bv) return -1;
  return koCollator.compare(av, bv) * dir;
}

function compareDate(
  a: string | null,
  b: string | null,
  dir: number,
): number {
  if (!a && !b) return 0;
  if (!a) return 1;
  if (!b) return -1;
  return a.localeCompare(b) * dir;
}

function compareNumber(
  a: number | null,
  b: number | null,
  dir: number,
): number {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  return (a - b) * dir;
}

function clientLabel(p: Project): string {
  return p.client_names.length > 0
    ? p.client_names.join(", ")
    : p.client_text;
}

function collectionRateNumber(p: Project): number | null {
  return typeof p.collection_rate === "number" ? p.collection_rate : null;
}

export default function ProjectsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  // admin/team_lead/manager 진입 가능 (사용자 결정 2026-05-15 — 팀장 추가)
  // — 일반직원(member)은 /me로 redirect
  const { user, allowed } = useRoleGuard(["admin", "team_lead", "manager"]);
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
  const [sort, setSort] = useState<SortState>(() => loadSavedSort());
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
      sortKey: sort.key,
      sortDir: sort.dir,
      view,
      activePreset,
      visibleCount,
    };
    window.sessionStorage.setItem(SS_KEY, JSON.stringify(next));
  }, [filter, sort, view, activePreset, visibleCount]);

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

  const updateSort = (next: SortState): void => {
    setSort(next);
    setVisibleCount(PAGE_SIZE);
  };

  const updateTableSort = (key: ProjectTableSortKey): void => {
    setSort((current) => ({
      key,
      dir:
        current.key === key
          ? current.dir === "asc"
            ? "desc"
            : "asc"
          : defaultSortDir(key),
    }));
    setVisibleCount(PAGE_SIZE);
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
    const dir = sort.dir === "asc" ? 1 : -1;
    const stageOrder = (stage: string): number => {
      const i = (PROJECT_STAGES as readonly string[]).indexOf(stage);
      return i === -1 ? PROJECT_STAGES.length : i;
    };
    sorted.sort((a, b) => {
      switch (sort.key) {
        case "start_date":
          return compareDate(a.start_date, b.start_date, dir);
        case "code":
          return compareText(a.code, b.code, dir);
        case "name":
          return compareText(a.name, b.name, dir);
        case "stage":
          return (stageOrder(a.stage) - stageOrder(b.stage)) * dir;
        case "client":
          return compareText(clientLabel(a), clientLabel(b), dir);
        case "team":
          return compareText(a.teams.join(", "), b.teams.join(", "), dir);
        case "assignees":
          return compareText(
            a.assignees.join(", "),
            b.assignees.join(", "),
            dir,
          );
        case "contract_period": {
          const start = compareDate(a.contract_start, b.contract_start, dir);
          if (start !== 0) return start;
          return compareDate(a.contract_end, b.contract_end, dir);
        }
        case "amount":
          return compareNumber(a.contract_amount, b.contract_amount, dir);
        case "collection_rate":
          return compareNumber(
            collectionRateNumber(a),
            collectionRateNumber(b),
            dir,
          );
      }
    });
    return sorted;
  }, [all, filter, sort, teamsMap, activePreset, presetCtx]);

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
                value={sortOptionValue(sort)}
                onChange={(e) => {
                  updateSort(parseSortOptionValue(e.target.value));
                }}
                className="rounded-md border border-zinc-300 bg-white px-2.5 py-1 outline-none dark:border-zinc-700 dark:bg-zinc-950"
              >
                {SORT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
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
              sortKey={isProjectTableSortKey(sort.key) ? sort.key : null}
              sortDir={sort.dir}
              onSortChange={updateTableSort}
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
