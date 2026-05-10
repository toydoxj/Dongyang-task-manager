"use client";

import Link from "next/link";

import type { Project, Task } from "@/lib/domain";
import { cn } from "@/lib/utils";

interface Props {
  /** 본인(또는 ?as 대상) 담당 프로젝트 (진행중·대기). */
  projects: Project[];
  /** 본인 담당 TASK (완료 cutoff 적용 후). */
  tasks: Task[];
}

const DUE_SOON_DAYS = 7;

function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

interface Snapshot {
  project: Project;
  inProgress: number;
  dueSoon: number;
  overdue: number;
  lastActivity: string | null;
}

/** MY-004 — 담당 프로젝트별 task 진행 요약 카드. */
export default function MyProjectSnapshots({ projects, tasks }: Props) {
  if (projects.length === 0) return null;

  const today = new Date();
  const todayStr = ymd(today);
  const dueEnd = new Date(today);
  dueEnd.setDate(dueEnd.getDate() + DUE_SOON_DAYS);
  const dueEndStr = ymd(dueEnd);

  // 한 번 순회로 project별 task 집계 (N+M 대신 O(M))
  const byProject = new Map<string, Task[]>();
  for (const t of tasks) {
    for (const pid of t.project_ids) {
      const list = byProject.get(pid) ?? [];
      list.push(t);
      byProject.set(pid, list);
    }
  }

  const snapshots: Snapshot[] = projects.map((p) => {
    const pts = byProject.get(p.id) ?? [];
    let inProgress = 0;
    let dueSoon = 0;
    let overdue = 0;
    let lastActivity: string | null = null;
    for (const t of pts) {
      if (t.status === "진행 중") inProgress += 1;
      if (t.status !== "완료" && t.end_date != null) {
        const d = t.end_date.slice(0, 10);
        if (d < todayStr) overdue += 1;
        else if (d <= dueEndStr) dueSoon += 1;
      }
      const ref = t.last_edited_time ?? t.actual_end_date;
      if (ref && (!lastActivity || ref > lastActivity)) lastActivity = ref;
    }
    return { project: p, inProgress, dueSoon, overdue, lastActivity };
  });

  // overdue + dueSoon이 큰 순 → 즉시 손볼 것 위로
  snapshots.sort((a, b) => {
    const aw = a.overdue * 10 + a.dueSoon;
    const bw = b.overdue * 10 + b.dueSoon;
    if (aw !== bw) return bw - aw;
    return (b.lastActivity ?? "").localeCompare(a.lastActivity ?? "");
  });

  return (
    <section>
      <h2 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
        프로젝트 스냅샷 ({snapshots.length})
        <span className="ml-2 text-[11px] font-normal text-zinc-500">
          담당 프로젝트별 TASK 진행 요약 — 손볼 일이 많은 순
        </span>
      </h2>
      <div className="grid grid-cols-1 gap-2 md:grid-cols-2 lg:grid-cols-3">
        {snapshots.map((s) => (
          <SnapshotCard key={s.project.id} snapshot={s} />
        ))}
      </div>
    </section>
  );
}

function SnapshotCard({ snapshot }: { snapshot: Snapshot }) {
  const { project: p, inProgress, dueSoon, overdue, lastActivity } = snapshot;
  return (
    <Link
      href={`/projects/${p.id}`}
      className="block rounded-xl border border-zinc-200 bg-white p-3 transition-colors hover:border-zinc-300 hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:border-zinc-700 dark:hover:bg-zinc-800"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="font-mono text-[10px] text-zinc-500">
            {p.code || "—"}
          </p>
          <h3 className="mt-0.5 truncate text-sm font-semibold text-zinc-900 dark:text-zinc-100">
            {p.name || "(제목 없음)"}
          </h3>
        </div>
        <span
          className={cn(
            "rounded-md border px-1.5 py-0.5 text-[10px] font-medium",
            p.stage === "진행중"
              ? "border-blue-500/30 bg-blue-500/15 text-blue-400"
              : "border-purple-500/30 bg-purple-500/15 text-purple-400",
          )}
        >
          {p.stage}
        </span>
      </div>
      <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
        <Stat label="진행 중" value={inProgress} tone="neutral" />
        <Stat label="임박" value={dueSoon} tone={dueSoon > 0 ? "warn" : "neutral"} />
        <Stat label="지연" value={overdue} tone={overdue > 0 ? "danger" : "neutral"} />
      </div>
      {lastActivity && (
        <p className="mt-2 text-[10px] text-zinc-500">
          최근 활동 {lastActivity.slice(0, 10)}
        </p>
      )}
    </Link>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "neutral" | "warn" | "danger";
}) {
  const cls =
    tone === "danger"
      ? "bg-red-100 text-red-800 dark:bg-red-500/20 dark:text-red-300"
      : tone === "warn"
        ? "bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-300"
        : "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300";
  return (
    <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 ${cls}`}>
      <span className="text-[9px] opacity-80">{label}</span>
      <strong>{value}</strong>
    </span>
  );
}
