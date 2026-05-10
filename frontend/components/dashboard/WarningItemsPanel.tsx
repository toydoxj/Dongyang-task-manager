"use client";

import Link from "next/link";

import type { Project } from "@/lib/domain";

interface Props {
  projects: Project[];
}

// 임계값 (Phase 1 PROJ-001 컨벤션과 통일)
const STALE_DAYS = 90;
const INCOME_ISSUE_RATIO = 0.3;
const TOP_N = 12;

function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

type WarnFlag = "stalled" | "noAssignee" | "incomeIssue" | "overdue";

/** DASH-004 — 모니터링용 경고 묶음 표. 액션 패널과 달리 "주의 깊게 보세요" 영역. */
export default function WarningItemsPanel({ projects }: Props) {
  const today = new Date();
  const todayStr = ymd(today);
  const staleCutoff = new Date(today);
  staleCutoff.setDate(staleCutoff.getDate() - STALE_DAYS);
  const staleCutoffStr = ymd(staleCutoff);

  const closedStages = new Set(["완료", "타절", "종결", "이관"]);

  // 한 프로젝트가 다중 경고를 가질 수 있음 — 모은 뒤 비어있지 않은 것만.
  const rows = projects
    .filter((p) => !closedStages.has(p.stage))
    .map((p) => {
      const flags = new Set<WarnFlag>();
      if (
        (p.stage === "진행중" || p.stage === "대기") &&
        p.start_date != null &&
        p.start_date.slice(0, 10) <= staleCutoffStr
      ) {
        flags.add("stalled");
      }
      if (p.assignees.length === 0) flags.add("noAssignee");
      if (
        p.contract_signed &&
        p.contract_amount != null &&
        p.contract_amount > 0 &&
        (p.collection_total ?? 0) < p.contract_amount * INCOME_ISSUE_RATIO
      ) {
        flags.add("incomeIssue");
      }
      if (
        p.contract_end != null &&
        p.contract_end.slice(0, 10) < todayStr &&
        p.stage === "진행중"
      ) {
        flags.add("overdue");
      }
      return { project: p, flags };
    })
    .filter((r) => r.flags.size > 0)
    .sort((a, b) => b.flags.size - a.flags.size)
    .slice(0, TOP_N);

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
          {rows.map(({ project: p, flags }) => (
            <li key={p.id}>
              <Link
                href={`/projects/${p.id}`}
                className="flex items-center gap-2 py-1.5 text-xs hover:bg-zinc-50 dark:hover:bg-zinc-800/40"
              >
                <span
                  className="flex-1 truncate font-medium text-zinc-800 dark:text-zinc-200"
                  title={p.name}
                >
                  {p.name || "(제목 없음)"}
                </span>
                <div className="flex shrink-0 gap-1">
                  {flags.has("stalled") && <Chip label="정체" tone="amber" />}
                  {flags.has("overdue") && <Chip label="기한 초과" tone="red" />}
                  {flags.has("noAssignee") && (
                    <Chip label="담당 미정" tone="zinc" />
                  )}
                  {flags.has("incomeIssue") && (
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
