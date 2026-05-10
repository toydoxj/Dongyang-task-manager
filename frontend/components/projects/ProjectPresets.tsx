"use client";

import { cn } from "@/lib/utils";

export type PresetKey =
  | "inProgress"
  | "thisWeekStart"
  | "dueSoon"
  | "stalled"
  | "myTeam"
  | "sealActive"
  | "incomeIssue"
  | "recentEdit";

interface Preset {
  key: PresetKey;
  label: string;
  hint: string;
}

export const PRESETS: Preset[] = [
  { key: "inProgress", label: "진행중", hint: "stage = 진행중" },
  { key: "thisWeekStart", label: "이번주 시작", hint: "수주일 = 이번 주" },
  { key: "dueSoon", label: "완료 임박", hint: "계약종료 ≤ 30일" },
  { key: "stalled", label: "장기 정체", hint: "진행중·대기 + 90일 이상" },
  { key: "myTeam", label: "우리 팀", hint: "내 팀 담당 프로젝트" },
  { key: "sealActive", label: "날인 진행중", hint: "검토중인 날인 보유" },
  { key: "incomeIssue", label: "수금 이슈", hint: "용역비 대비 수금 < 30%" },
  { key: "recentEdit", label: "최근 수정", hint: "지난 7일 변경" },
];

interface Props {
  activeKey: PresetKey | null;
  onChange: (key: PresetKey | null) => void;
  counts?: Partial<Record<PresetKey, number>>;
}

export default function ProjectPresets({
  activeKey,
  onChange,
  counts,
}: Props) {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-xl border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900">
      <span className="text-[11px] font-medium text-zinc-500">프리셋</span>
      <button
        type="button"
        onClick={() => onChange(null)}
        className={chipClass(activeKey === null)}
        title="모든 프리셋 해제"
      >
        전체
      </button>
      {PRESETS.map((p) => {
        const active = activeKey === p.key;
        const count = counts?.[p.key];
        return (
          <button
            key={p.key}
            type="button"
            onClick={() => onChange(active ? null : p.key)}
            title={p.hint}
            className={chipClass(active)}
          >
            <span>{p.label}</span>
            {count !== undefined && (
              <span
                className={cn(
                  "ml-1.5 rounded px-1 text-[10px] font-medium",
                  active
                    ? "bg-zinc-700 text-white dark:bg-zinc-300 dark:text-zinc-900"
                    : "bg-zinc-200 text-zinc-600 dark:bg-zinc-700 dark:text-zinc-300",
                )}
              >
                {count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

function chipClass(active: boolean): string {
  return cn(
    "inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors",
    active
      ? "border-zinc-900 bg-zinc-900 text-white dark:border-zinc-200 dark:bg-zinc-100 dark:text-zinc-900"
      : "border-zinc-300 bg-white text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-300 dark:hover:bg-zinc-800",
  );
}
