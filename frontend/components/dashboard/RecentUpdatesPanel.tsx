"use client";

import Link from "next/link";

import type { Project } from "@/lib/domain";

interface Props {
  projects: Project[];
}

const RECENT_DAYS = 7;
const TOP_N = 10;

function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** DASH-004 — 최근 7일 안에 변경된 프로젝트 Top N. last_edited_time 내림차순. */
export default function RecentUpdatesPanel({ projects }: Props) {
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - RECENT_DAYS);
  const cutoffStr = ymd(cutoff);

  const recent = projects
    .filter(
      (p) =>
        p.last_edited_time != null &&
        p.last_edited_time.slice(0, 10) >= cutoffStr,
    )
    .sort((a, b) =>
      (b.last_edited_time ?? "").localeCompare(a.last_edited_time ?? ""),
    )
    .slice(0, TOP_N);

  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <header className="mb-3">
        <h3 className="text-sm font-semibold">최근 변경 프로젝트</h3>
        <p className="text-[11px] text-zinc-500">
          지난 {RECENT_DAYS}일 이내 노션 변경 — Top {TOP_N}
        </p>
      </header>
      {recent.length === 0 ? (
        <p className="py-6 text-center text-xs text-zinc-500">
          최근 {RECENT_DAYS}일 동안 변경된 프로젝트가 없습니다.
        </p>
      ) : (
        <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
          {recent.map((p) => (
            <li key={p.id}>
              <Link
                href={`/projects/${p.id}`}
                className="flex items-center gap-2 py-1.5 text-xs hover:bg-zinc-50 dark:hover:bg-zinc-800/40"
              >
                <span className="font-mono text-[10px] text-zinc-500">
                  {p.code || "—"}
                </span>
                <span
                  className="flex-1 truncate font-medium text-zinc-800 dark:text-zinc-200"
                  title={p.name}
                >
                  {p.name || "(제목 없음)"}
                </span>
                <span className="font-mono text-[10px] text-zinc-500">
                  {(p.last_edited_time ?? "").slice(5, 10).replace("-", "/")}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
