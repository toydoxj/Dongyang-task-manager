"use client";

import type { Project, Task } from "@/lib/domain";
import { formatPercent, formatWon } from "@/lib/format";
import { cn } from "@/lib/utils";

interface Props {
  project: Project;
  tasks: Task[];
}

/** 0~1. 완료=100%, 진행 중=task 진행률 평균, 시작 전=0. */
function computeProjectProgress(tasks: Task[]): number | null {
  if (tasks.length === 0) return null;
  const sum = tasks.reduce((s, t) => {
    if (t.status === "완료") return s + 1;
    if (t.status === "시작 전") return s + 0;
    return s + (t.progress ?? 0);
  }, 0);
  return sum / tasks.length;
}

export default function ProgressOverview({ project, tasks }: Props) {
  const progress = computeProjectProgress(tasks);
  const collectionRate =
    typeof project.collection_rate === "number" ? project.collection_rate : null;

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <h3 className="mb-4 text-sm font-semibold">진행률 종합</h3>

      <div className="grid grid-cols-2 gap-4">
        <Gauge
          value={progress}
          label="프로젝트 진행률"
          caption={`업무TASK ${tasks.length}건 평균`}
          color="text-blue-500"
        />
        <Gauge
          value={collectionRate}
          label="수금률"
          caption={`수금합 / 용역비 = ${formatWon(project.collection_total, true)} / ${formatWon(project.contract_amount, true)}`}
          color="text-emerald-500"
        />
      </div>
    </div>
  );
}

function Gauge({
  value,
  label,
  caption,
  color,
}: {
  value: number | null;
  label: string;
  caption: string;
  color: string;
}) {
  // 0~1 → angle 0~360 (시계방향)
  const r = 36;
  const c = 2 * Math.PI * r;
  const safe = value ?? 0;
  const offset = c * (1 - safe);

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative h-28 w-28">
        <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90">
          <circle
            cx="50"
            cy="50"
            r={r}
            fill="none"
            stroke="currentColor"
            className="text-zinc-200 dark:text-zinc-800"
            strokeWidth="9"
          />
          <circle
            cx="50"
            cy="50"
            r={r}
            fill="none"
            stroke="currentColor"
            className={cn(color, value == null && "opacity-30")}
            strokeWidth="9"
            strokeDasharray={c}
            strokeDashoffset={offset}
            strokeLinecap="round"
            style={{ transition: "stroke-dashoffset 0.5s" }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-xl font-semibold">
            {formatPercent(value)}
          </span>
        </div>
      </div>
      <p className="text-xs font-medium text-zinc-700 dark:text-zinc-300">
        {label}
      </p>
      <p className="text-center text-[10px] leading-tight text-zinc-500">
        {caption}
      </p>
    </div>
  );
}
