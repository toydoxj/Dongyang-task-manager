"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";

import ProjectCard from "@/components/projects/ProjectCard";
import ProjectFilter, {
  type FilterState,
} from "@/components/projects/ProjectFilter";
import LoadingState from "@/components/ui/LoadingState";
import { getEmployeeTeamsMap } from "@/lib/api";
import { useProjects } from "@/lib/hooks";

const PAGE_SIZE = 60;

type SortKey = "start_desc" | "start_asc" | "name_asc" | "amount_desc";

/** 시작일 내림차순 비교 (null은 항상 뒤로). */
function cmpDateDesc(a: string | null, b: string | null): number {
  if (!a && !b) return 0;
  if (!a) return 1;
  if (!b) return -1;
  return b.localeCompare(a);
}

export default function ProjectsPage() {
  const { data, error } = useProjects();
  const all = data?.items;
  // 직원 명부의 assignee.team 으로 프로젝트 팀을 자동 집계 (노션 '담당팀' 누락 보완).
  const { data: teamsMap } = useSWR(
    ["employee-teams-map"],
    () => getEmployeeTeamsMap(),
  );
  const [filter, setFilter] = useState<FilterState>({
    query: "",
    stage: "",
    team: "",
    completed: "open",
  });
  const [sortKey, setSortKey] = useState<SortKey>("start_desc");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  const updateFilter = (next: FilterState) => {
    setFilter(next);
    setVisibleCount(PAGE_SIZE);
  };

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
  }, [all, filter, sortKey, teamsMap]);

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
          <ProjectFilter
            value={filter}
            onChange={updateFilter}
            totalCount={all.length}
            filteredCount={filtered.length}
          />
          <div className="flex items-center gap-2 text-xs">
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
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            {filtered.slice(0, visibleCount).map((p) => (
              <ProjectCard key={p.id} project={p} />
            ))}
          </div>

          {filtered.length === 0 && (
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
