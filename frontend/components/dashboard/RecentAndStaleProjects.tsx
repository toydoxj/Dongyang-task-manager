"use client";

import Link from "next/link";

import type { Project } from "@/lib/domain";

interface Props {
  projects: Project[];
}

function startOfWeekMonday(d: Date): Date {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  const day = x.getDay() || 7; // 일요일(0)을 7로 취급해 월요일을 주의 시작으로
  x.setDate(x.getDate() - (day - 1));
  return x;
}

function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export default function RecentAndStaleProjects({ projects }: Props) {
  const today = new Date();
  const thisWeekStart = startOfWeekMonday(today);
  const lastWeekStart = new Date(thisWeekStart);
  lastWeekStart.setDate(lastWeekStart.getDate() - 7);
  const nextWeekStart = new Date(thisWeekStart);
  nextWeekStart.setDate(nextWeekStart.getDate() + 7);

  const thisWeekStr = ymd(thisWeekStart);
  const lastWeekStr = ymd(lastWeekStart);
  const nextWeekStr = ymd(nextWeekStart);

  const thisWeek: Project[] = [];
  const lastWeek: Project[] = [];
  for (const p of projects) {
    if (!p.start_date) continue;
    const s = p.start_date.slice(0, 10);
    if (s >= thisWeekStr && s < nextWeekStr) thisWeek.push(p);
    else if (s >= lastWeekStr && s < thisWeekStr) lastWeek.push(p);
  }
  const sortDesc = (a: Project, b: Project) =>
    (b.start_date ?? "").localeCompare(a.start_date ?? "");
  thisWeek.sort(sortDesc);
  lastWeek.sort(sortDesc);

  // 3개월 이상 대기 — 현재 stage='대기' + 수주일이 cutoff 이전
  const threeMonthsAgo = new Date();
  threeMonthsAgo.setMonth(threeMonthsAgo.getMonth() - 3);
  const cutoff = ymd(threeMonthsAgo);
  const staleWaiting = projects
    .filter((p) => {
      if (p.stage !== "대기") return false;
      if (!p.start_date) return false;
      return p.start_date.slice(0, 10) <= cutoff;
    })
    .sort((a, b) => (a.start_date ?? "").localeCompare(b.start_date ?? ""));

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <Card
        title="이번주 / 저번주 신규 프로젝트"
        subtitle={`수주일 기준 · ${lastWeekStr} ~`}
      >
        <Group label="이번주" count={thisWeek.length} items={thisWeek} />
        <Group label="저번주" count={lastWeek.length} items={lastWeek} />
      </Card>
      <Card
        title="3개월 이상 대기 프로젝트"
        subtitle={`수주일 ${cutoff} 이전 + 현재 '대기'`}
      >
        {staleWaiting.length === 0 ? (
          <p className="px-2 py-6 text-center text-xs text-zinc-400">
            해당 없음
          </p>
        ) : (
          <ul className="space-y-1">
            {staleWaiting.map((p) => (
              <ProjectRow key={p.id} project={p} />
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function Card({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex h-full max-h-[480px] flex-col rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <header className="mb-3 shrink-0">
        <h3 className="text-sm font-semibold">{title}</h3>
        {subtitle && <p className="text-[11px] text-zinc-500">{subtitle}</p>}
      </header>
      <div className="flex-1 space-y-3 overflow-y-auto pr-1">{children}</div>
    </section>
  );
}

function Group({
  label,
  count,
  items,
}: {
  label: string;
  count: number;
  items: Project[];
}) {
  return (
    <div>
      <h4 className="mb-1 flex items-center gap-1 text-[11px] font-medium text-zinc-500">
        <span>{label}</span>
        <span className="text-zinc-400">({count})</span>
      </h4>
      {items.length === 0 ? (
        <p className="py-2 text-center text-[11px] text-zinc-400">없음</p>
      ) : (
        <ul className="space-y-1">
          {items.map((p) => (
            <ProjectRow key={p.id} project={p} />
          ))}
        </ul>
      )}
    </div>
  );
}

function ProjectRow({ project }: { project: Project }) {
  return (
    <li>
      <Link
        href={`/project?id=${project.id}`}
        className="flex items-center gap-2 rounded-md border border-zinc-200 bg-zinc-50/60 px-2 py-1.5 text-xs transition-colors hover:bg-zinc-100 dark:border-zinc-800 dark:bg-zinc-950/60 dark:hover:bg-zinc-800"
      >
        <span
          className="flex-1 truncate font-medium text-zinc-800 dark:text-zinc-200"
          title={project.name}
        >
          {project.name || "(제목 없음)"}
        </span>
        {project.start_date && (
          <span className="font-mono text-[10px] text-zinc-500">
            {project.start_date.slice(2, 10).replace(/-/g, ".")}
          </span>
        )}
        <span className="text-[10px] text-zinc-500">
          {project.assignees.length > 0
            ? project.assignees.length === 1
              ? project.assignees[0]
              : `${project.assignees[0]} +${project.assignees.length - 1}`
            : "—"}
        </span>
      </Link>
    </li>
  );
}
