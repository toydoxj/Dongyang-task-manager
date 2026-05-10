"use client";

/**
 * 프로젝트 담당 이력 — 수평 Gantt swim lane.
 *
 * 데이터: assign log (`/api/projects/{id}/log`) — '담당 추가' / '담당 제거'
 * 이벤트가 시간순 ascending. 각 담당자별로 (start, end) segments 로 변환.
 *
 * 진행 중인 segment 는 끝에 → 화살표 + dashed 로 표시.
 * 시간축은 프로젝트 시작일 ~ max(오늘, 마지막 이벤트). LifecycleTimeline 과
 * 일관된 좌표계로 두면 한 화면에서 비교 가능.
 */

import { useMemo } from "react";

import type { ProjectLogEntry } from "@/lib/api";
import type { Project } from "@/lib/domain";
import { cn } from "@/lib/utils";

interface Props {
  project: Project;
  logs: ProjectLogEntry[];
}

interface Segment {
  startMs: number;
  endMs: number;
  open: boolean; // 진행 중 (제거 이벤트 없음)
  startActor: string;
  endActor: string;
  startEventAt: string;
  endEventAt: string;
}

interface Lane {
  name: string;
  segments: Segment[];
}

// 담당자별 색 — name 해시로 deterministic 매핑
const PALETTE = [
  "bg-blue-500",
  "bg-emerald-500",
  "bg-violet-500",
  "bg-amber-500",
  "bg-pink-500",
  "bg-cyan-500",
  "bg-rose-500",
  "bg-teal-500",
  "bg-orange-500",
  "bg-indigo-500",
];

function colorFor(name: string): string {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) | 0;
  return PALETTE[Math.abs(h) % PALETTE.length];
}

function parseMs(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  return Number.isFinite(t) ? t : null;
}

function formatYMD(ms: number): string {
  const d = new Date(ms);
  const y = String(d.getFullYear()).slice(2);
  const mo = String(d.getMonth() + 1).padStart(2, "0");
  const da = String(d.getDate()).padStart(2, "0");
  return `${y}.${mo}.${da}`;
}

export default function AssigneeTimeline({ project, logs }: Props) {
  // Date.now() / let 변수 mutation — useMemo 룰(purity)이 엄격하게 잡지만
  // segment 누적 알고리즘 본질상 임시 mutable Map과 시점 timestamp가 필요.
  // 결과는 deterministic (logs/project 변경 시 재계산).
  /* eslint-disable react-hooks/purity */
  const { lanes, minMs, maxMs } = useMemo(() => {
    // 1) 시간순 누적해 segments 생성
    const open: Map<string, Segment> = new Map();
    const closed: Map<string, Segment[]> = new Map();
    for (const e of logs) {
      const at = parseMs(e.event_at);
      if (!at) continue;
      const target = e.target?.trim();
      if (!target) continue;
      const list = closed.get(target) ?? [];
      if (e.action === "담당 추가") {
        // 이미 진행 중이면 무시 (중복 추가)
        if (open.has(target)) continue;
        open.set(target, {
          startMs: at,
          endMs: at,
          open: true,
          startActor: e.actor || "",
          endActor: "",
          startEventAt: e.event_at,
          endEventAt: "",
        });
      } else if (e.action === "담당 제거") {
        const seg = open.get(target);
        if (seg) {
          seg.endMs = at;
          seg.open = false;
          seg.endActor = e.actor || "";
          seg.endEventAt = e.event_at;
          list.push(seg);
          open.delete(target);
        } else {
          // 추가 이벤트 없이 제거된 경우 — 시작일을 프로젝트 시작일로 가정
          const projStart = parseMs(project.start_date);
          list.push({
            startMs: projStart ?? at,
            endMs: at,
            open: false,
            startActor: "",
            endActor: e.actor || "",
            startEventAt: project.start_date ?? "",
            endEventAt: e.event_at,
          });
        }
      }
      closed.set(target, list);
    }

    // 2) 현재 assignees 중 open segment 없는 사람은 implicit "프로젝트 시작부터 진행 중"
    const projStart = parseMs(project.start_date);
    for (const name of project.assignees) {
      if (open.has(name)) continue;
      const segs = closed.get(name);
      // 이미 closed segment가 있는데 open이 없으면 (= 마지막 이벤트가 제거)
      // 다시 추가됐다는 정보가 없는 한 진행 중으로 표시 안 함
      if (segs && segs.length > 0) continue;
      // log가 전혀 없는 사람 → 처음부터 담당
      open.set(name, {
        startMs: projStart ?? Date.now(),
        endMs: Date.now(),
        open: true,
        startActor: "",
        endActor: "",
        startEventAt: project.start_date ?? "",
        endEventAt: "",
      });
    }

    // 3) Lane 으로 합치기
    const lanesMap = new Map<string, Segment[]>();
    for (const [name, list] of closed.entries()) {
      lanesMap.set(name, [...list]);
    }
    for (const [name, seg] of open.entries()) {
      const list = lanesMap.get(name) ?? [];
      list.push(seg);
      lanesMap.set(name, list);
    }

    // 4) 시간 범위 — 프로젝트 시작일/완료일 + 모든 segment 양 끝
    let minMs = projStart ?? Date.now();
    let maxMs = Date.now();
    const projEnd = parseMs(project.end_date);
    if (projEnd) maxMs = Math.max(maxMs, projEnd);
    for (const [, segs] of lanesMap) {
      for (const s of segs) {
        if (s.startMs < minMs) minMs = s.startMs;
        if (s.endMs > maxMs) maxMs = s.endMs;
      }
    }
    if (maxMs - minMs < 86400000) maxMs = minMs + 86400000; // 최소 1일 폭

    // 5) 정렬: 첫 segment 시작일 asc → 진행 중인 사람이 먼저 보이게
    const lanes: Lane[] = Array.from(lanesMap.entries())
      .map(([name, segments]) => ({
        name,
        segments: segments.slice().sort((a, b) => a.startMs - b.startMs),
      }))
      .sort((a, b) => {
        const aStart = a.segments[0]?.startMs ?? Number.MAX_SAFE_INTEGER;
        const bStart = b.segments[0]?.startMs ?? Number.MAX_SAFE_INTEGER;
        return aStart - bStart;
      });

    return { lanes, minMs, maxMs };
  }, [project, logs]);
  /* eslint-enable react-hooks/purity */

  if (lanes.length === 0) {
    return null;
  }

  const range = maxMs - minMs;
  const xPct = (ms: number): number =>
    Math.max(0, Math.min(100, ((ms - minMs) / range) * 100));

  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
      <header className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold">담당 이력</h2>
          <p className="text-[11px] text-zinc-500">
            담당 추가 → 해제 구간을 swim lane 으로 표시. 진행 중은 끝에 →.
          </p>
        </div>
        <span className="text-[10px] text-zinc-400">
          {formatYMD(minMs)} ~ {formatYMD(maxMs)}
        </span>
      </header>

      <div className="space-y-1.5">
        {lanes.map((lane) => {
          const color = colorFor(lane.name);
          return (
            <div key={lane.name} className="flex items-center gap-2">
              <span className="w-16 shrink-0 truncate text-xs text-zinc-700 dark:text-zinc-300">
                {lane.name}
              </span>
              <div className="relative h-3 flex-1 rounded bg-zinc-100 dark:bg-zinc-800">
                {lane.segments.map((s, i) => {
                  const left = xPct(s.startMs);
                  const right = xPct(s.endMs);
                  const width = Math.max(0.5, right - left);
                  const tip = [
                    `시작: ${formatYMD(s.startMs)}${
                      s.startActor ? ` (지정: ${s.startActor})` : ""
                    }`,
                    s.open
                      ? "현재 진행 중"
                      : `종료: ${formatYMD(s.endMs)}${
                          s.endActor ? ` (해제: ${s.endActor})` : ""
                        }`,
                  ].join("\n");
                  return (
                    <div
                      key={i}
                      className={cn(
                        "absolute top-1 flex h-1.5 items-center rounded-sm text-[9px] text-white",
                        color,
                        s.open ? "border-r-2 border-dashed border-white" : "",
                      )}
                      style={{ left: `${left}%`, width: `${width}%` }}
                      title={tip}
                    />
                  );
                })}
                {lane.segments
                  .filter((s) => s.open)
                  .map((s, i) => (
                    <span
                      key={`arrow-${i}`}
                      className="absolute top-0 text-[10px] leading-3 text-zinc-500"
                      style={{ left: `calc(${xPct(s.endMs)}% + 1px)` }}
                    >
                      →
                    </span>
                  ))}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
