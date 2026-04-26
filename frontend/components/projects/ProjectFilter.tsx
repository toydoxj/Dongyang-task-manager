"use client";

import { PROJECT_STAGES, TEAMS } from "@/lib/domain";
import { cn } from "@/lib/utils";

export interface FilterState {
  query: string;
  stage: string;
  team: string;
  completed: "all" | "open" | "done";
}

interface Props {
  value: FilterState;
  onChange: (next: FilterState) => void;
  totalCount: number;
  filteredCount: number;
}

export default function ProjectFilter({
  value,
  onChange,
  totalCount,
  filteredCount,
}: Props) {
  return (
    <div className="space-y-3 rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex flex-col gap-3 md:flex-row md:items-center">
        <input
          type="search"
          placeholder="프로젝트명 또는 코드로 검색…"
          value={value.query}
          onChange={(e) => onChange({ ...value, query: e.target.value })}
          className="flex-1 rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm outline-none focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-950"
        />
        <span className="text-xs text-zinc-500">
          {filteredCount.toLocaleString()} / {totalCount.toLocaleString()} 건
        </span>
      </div>

      <div className="flex flex-wrap gap-2">
        <Chip
          active={value.completed === "all"}
          onClick={() => onChange({ ...value, completed: "all" })}
        >
          전체
        </Chip>
        <Chip
          active={value.completed === "open"}
          onClick={() => onChange({ ...value, completed: "open" })}
        >
          미완료
        </Chip>
        <Chip
          active={value.completed === "done"}
          onClick={() => onChange({ ...value, completed: "done" })}
        >
          완료
        </Chip>
        <span className="mx-1 self-center text-zinc-300 dark:text-zinc-700">
          |
        </span>

        <Chip
          active={value.stage === ""}
          onClick={() => onChange({ ...value, stage: "" })}
        >
          모든 단계
        </Chip>
        {PROJECT_STAGES.map((s) => (
          <Chip
            key={s}
            active={value.stage === s}
            onClick={() => onChange({ ...value, stage: s })}
          >
            {s}
          </Chip>
        ))}
        <span className="mx-1 self-center text-zinc-300 dark:text-zinc-700">
          |
        </span>

        <Chip
          active={value.team === ""}
          onClick={() => onChange({ ...value, team: "" })}
        >
          모든 팀
        </Chip>
        {TEAMS.map((t) => (
          <Chip
            key={t}
            active={value.team === t}
            onClick={() => onChange({ ...value, team: t })}
          >
            {t}
          </Chip>
        ))}
      </div>
    </div>
  );
}

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-md border px-2.5 py-1 text-xs transition-colors",
        active
          ? "border-zinc-900 bg-zinc-900 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-900"
          : "border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-300 dark:hover:bg-zinc-900",
      )}
    >
      {children}
    </button>
  );
}
