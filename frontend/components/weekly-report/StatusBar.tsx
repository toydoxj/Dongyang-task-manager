"use client";

import type { WeeklyReport } from "@/lib/api";

interface Props {
  data: WeeklyReport | null;
  isAdmin: boolean;
}

/** WEEK-001 상단 진행 상태 바 — 데이터 수집/검토/수동 입력/발행 가능 여부를 1줄로 요약. */
export default function StatusBar({ data, isAdmin }: Props) {
  // 데이터 수집 — fetch 성공 여부
  const collected = data != null;

  // 자동 집계 0건 섹션 (자동 집계인데 비어있어 검토가 필요할 수 있음)
  const autoEmpty = data
    ? [
        ["완료 프로젝트", data.completed.length],
        ["날인대장", data.seal_log.length],
        ["영업", data.sales.length],
        ["신규 프로젝트", data.new_projects.length],
      ].filter(([, n]) => (n as number) === 0).length
    : 0;

  // 수동 입력 비어있음 (공지/교육/건의 — 운영자가 직접 등록)
  const manualEmpty = data
    ? (data.notices.length === 0 ? 1 : 0) +
      (data.education.length === 0 ? 1 : 0) +
      (data.suggestions.length === 0 ? 1 : 0)
    : 3;

  // 발행 가능 — admin && data ready
  const publishReady = isAdmin && collected;

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex flex-wrap items-center gap-3 text-xs">
        <Pill
          label="데이터 수집"
          value={collected ? "완료" : "진행중"}
          tone={collected ? "good" : "neutral"}
        />
        <Pill
          label="검토 필요"
          value={`${autoEmpty}건`}
          hint="자동 집계 0건 섹션"
          tone={autoEmpty > 0 ? "warn" : "neutral"}
        />
        <Pill
          label="수동 입력 필요"
          value={`${manualEmpty}건`}
          hint="공지·교육·건의 미입력"
          tone={manualEmpty > 0 ? "warn" : "good"}
        />
        <Pill
          label="발행"
          value={publishReady ? "준비됨" : isAdmin ? "데이터 대기" : "권한 없음"}
          tone={publishReady ? "good" : "neutral"}
        />
      </div>
    </div>
  );
}

type Tone = "neutral" | "warn" | "good";

function Pill({
  label,
  value,
  hint,
  tone = "neutral",
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: Tone;
}) {
  const toneClass =
    tone === "warn"
      ? "border-amber-500/50 bg-amber-50 text-amber-800 dark:bg-amber-500/10 dark:text-amber-300"
      : tone === "good"
        ? "border-emerald-500/50 bg-emerald-50 text-emerald-800 dark:bg-emerald-500/10 dark:text-emerald-300"
        : "border-zinc-300 bg-zinc-50 text-zinc-700 dark:border-zinc-700 dark:bg-zinc-800/50 dark:text-zinc-300";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 ${toneClass}`}
      title={hint}
    >
      <span className="text-[10px] font-medium opacity-80">{label}</span>
      <span className="font-semibold">{value}</span>
    </span>
  );
}
