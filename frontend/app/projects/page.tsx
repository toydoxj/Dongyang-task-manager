"use client";

import { useEffect, useMemo, useState } from "react";

import ProjectCard from "@/components/projects/ProjectCard";
import ProjectFilter, {
  type FilterState,
} from "@/components/projects/ProjectFilter";
import { listProjects } from "@/lib/api";
import type { Project } from "@/lib/domain";

const PAGE_SIZE = 60;

export default function ProjectsPage() {
  const [all, setAll] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterState>({
    query: "",
    stage: "",
    team: "",
    completed: "open",
  });
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  useEffect(() => {
    void (async () => {
      try {
        const r = await listProjects();
        setAll(r.items);
      } catch (err) {
        setError(err instanceof Error ? err.message : "데이터 로딩 실패");
      }
    })();
  }, []);

  // 필터 변경 시 visibleCount 도 리셋. setState in effect 방지를 위해 setter wrap.
  const updateFilter = (next: FilterState) => {
    setFilter(next);
    setVisibleCount(PAGE_SIZE);
  };

  const filtered = useMemo(() => {
    if (!all) return [];
    const q = filter.query.trim().toLowerCase();
    return all.filter((p) => {
      if (filter.completed === "open" && p.completed) return false;
      if (filter.completed === "done" && !p.completed) return false;
      if (filter.stage && p.stage !== filter.stage) return false;
      if (filter.team && !p.teams.includes(filter.team)) return false;
      if (q) {
        const hay = `${p.code} ${p.name}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [all, filter]);

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
          {error}
        </div>
      )}

      {all && (
        <ProjectFilter
          value={filter}
          onChange={updateFilter}
          totalCount={all.length}
          filteredCount={filtered.length}
        />
      )}

      {!all && !error && (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="h-32 animate-pulse rounded-xl border border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900"
            />
          ))}
        </div>
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
