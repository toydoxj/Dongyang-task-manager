"use client";

import Link from "next/link";

import type { WarningRow } from "@/lib/api";

const TOP_N = 12;

interface Props {
  rows: WarningRow[];
}

/** DASH-004 — 모니터링용 경고 묶음 표. backend 집계(/api/dashboard/insights). */
export default function WarningItemsPanel({ rows }: Props) {
  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <header className="mb-3">
        <h3 className="text-sm font-semibold">경고 항목</h3>
        <p className="text-[11px] text-zinc-500">
          정체·기한 초과·담당 미정·수금 지연 — Top {TOP_N} (경고 수 많은 순)
        </p>
      </header>
      {rows.length === 0 ? (
        <p className="py-6 text-center text-xs text-zinc-500">
          현재 경고 항목이 없습니다. 🎉
        </p>
      ) : (
        <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
          {rows.map((r) => (
            <li key={r.id}>
              <Link
                href={`/projects/${r.id}`}
                className="flex items-center gap-2 py-1.5 text-xs hover:bg-zinc-50 dark:hover:bg-zinc-800/40"
              >
                <span
                  className="flex-1 truncate font-medium text-zinc-800 dark:text-zinc-200"
                  title={r.name}
                >
                  {r.name || "(제목 없음)"}
                </span>
                <div className="flex shrink-0 gap-1">
                  {r.flags.includes("stalled") && (
                    <Chip label="정체" tone="amber" />
                  )}
                  {r.flags.includes("overdue") && (
                    <Chip label="기한 초과" tone="red" />
                  )}
                  {r.flags.includes("noAssignee") && (
                    <Chip label="담당 미정" tone="zinc" />
                  )}
                  {r.flags.includes("incomeIssue") && (
                    <Chip label="수금 지연" tone="red" />
                  )}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Chip({ label, tone }: { label: string; tone: "amber" | "red" | "zinc" }) {
  const cls =
    tone === "red"
      ? "bg-red-100 text-red-800 dark:bg-red-500/20 dark:text-red-300"
      : tone === "amber"
        ? "bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-300"
        : "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300";
  return (
    <span className={`rounded px-1.5 py-0.5 text-[9px] font-medium ${cls}`}>
      {label}
    </span>
  );
}
