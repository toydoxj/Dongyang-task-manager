"use client";

import { cn } from "@/lib/utils";

/**
 * COMMON-001 — 프로젝트 운영 stage 배지 표준 컴포넌트.
 *
 * 7개 stage 색상 매핑은 ProjectCard / ProjectTable / ProjectHeader 등 5+ 곳에서
 * 동일하게 중복되어 있던 것을 단일 source로 통합.
 *
 * 사용처: 프로젝트 카드/표/헤더. TASK status(`진행 중`/`대기` 띄어쓰기 다름)는
 * 별도 enum이므로 ProjectTaskRow/SaleTaskRow는 자체 STAGE_BADGE를 유지.
 */
const STAGE_BADGE_CLASS: Record<string, string> = {
  "진행중": "bg-blue-500/15 text-blue-400 border-blue-500/30",
  "대기": "bg-purple-500/15 text-purple-400 border-purple-500/30",
  "보류": "bg-pink-500/15 text-pink-400 border-pink-500/30",
  "완료": "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  "타절": "bg-red-500/15 text-red-400 border-red-500/30",
  "종결": "bg-zinc-500/15 text-zinc-400 border-zinc-500/30",
  "이관": "bg-zinc-400/15 text-zinc-400 border-zinc-400/30",
};

const FALLBACK = "border-zinc-500/30 bg-zinc-500/15 text-zinc-400";

interface Props {
  stage: string;
  /** 추가 className (size·padding override 등). */
  className?: string;
}

export default function StageBadge({ stage, className }: Props) {
  if (!stage) return null;
  return (
    <span
      className={cn(
        "rounded-md border px-2 py-0.5 text-[10px] font-medium",
        STAGE_BADGE_CLASS[stage] ?? FALLBACK,
        className,
      )}
    >
      {stage}
    </span>
  );
}
