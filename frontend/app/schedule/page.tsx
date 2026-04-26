"use client";

import { useMemo, useState } from "react";

import { useAuth } from "@/components/AuthGuard";
import TaskEditModal from "@/components/project/TaskEditModal";
import LoadingState from "@/components/ui/LoadingState";
import type { Task } from "@/lib/domain";
import { useTasks } from "@/lib/hooks";
import { cn } from "@/lib/utils";

export default function SchedulePage() {
  const { user } = useAuth();
  const [year, setYear] = useState(() => new Date().getFullYear());
  const [month, setMonth] = useState(() => new Date().getMonth()); // 0~11
  const [filterCategory, setFilterCategory] = useState<string>("전체");
  const [filterAssignee, setFilterAssignee] = useState<string>("전체");
  const [editing, setEditing] = useState<Task | null>(null);

  const { data, error, isLoading } = useTasks(
    { schedule_only: true },
    Boolean(user),
  );
  const allItems = useMemo(() => data?.items ?? [], [data]);

  // 직원 목록 (assignees union)
  const allAssignees = useMemo(() => {
    const s = new Set<string>();
    for (const t of allItems) for (const a of t.assignees) if (a) s.add(a);
    return Array.from(s).sort((a, b) => a.localeCompare(b, "ko"));
  }, [allItems]);

  const filtered = useMemo(() => {
    return allItems.filter((t) => {
      if (filterCategory !== "전체") {
        // 분류=X OR 활동=X
        const cat = t.category;
        const act = t.activity;
        if (filterCategory === "외근") {
          if (cat !== "외근" && act !== "외근") return false;
        } else if (filterCategory === "출장") {
          if (cat !== "출장" && act !== "출장") return false;
        } else if (filterCategory === "휴가") {
          if (cat !== "휴가") return false;
        }
      }
      if (filterAssignee !== "전체") {
        if (!t.assignees.includes(filterAssignee)) return false;
      }
      return true;
    });
  }, [allItems, filterCategory, filterAssignee]);

  // 해당 월의 셀 (전월 말일 ~ 다음달 초) — 7×6 grid
  const cells = useMemo(() => buildMonthGrid(year, month), [year, month]);

  // 셀별 task 매핑 (한 task가 여러 일에 걸칠 수 있음)
  const taskByDay = useMemo(() => {
    const map = new Map<string, Task[]>(); // key: 'YYYY-MM-DD'
    for (const t of filtered) {
      const start = isoToYmd(t.start_date);
      const end = isoToYmd(t.end_date) ?? start;
      if (!start) continue;
      let cur = ymdToDate(start);
      const last = ymdToDate(end ?? start);
      // safety: 한 task 최대 60일 펼침 방지 (휴가 5일짜리 등 일반적)
      let safety = 0;
      while (cur <= last && safety < 60) {
        const key = ymdString(cur);
        const arr = map.get(key) ?? [];
        arr.push(t);
        map.set(key, arr);
        cur = new Date(cur.getFullYear(), cur.getMonth(), cur.getDate() + 1);
        safety += 1;
      }
    }
    return map;
  }, [filtered]);

  const monthLabel = `${year}년 ${month + 1}월`;
  const today = new Date();
  const todayKey = ymdString(today);

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">팀 일정</h1>
        <p className="mt-1 text-sm text-zinc-500">
          외근·출장·휴가 일정을 한눈에 확인합니다. 직원/분류 필터로 좁힐 수 있어요.
        </p>
      </header>

      {/* 컨트롤바 */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => navigate(year, month, -1, setYear, setMonth)}
            className={navBtn}
          >
            ←
          </button>
          <h2 className="min-w-[110px] text-center text-base font-semibold">
            {monthLabel}
          </h2>
          <button
            type="button"
            onClick={() => navigate(year, month, 1, setYear, setMonth)}
            className={navBtn}
          >
            →
          </button>
          <button
            type="button"
            onClick={() => {
              const t = new Date();
              setYear(t.getFullYear());
              setMonth(t.getMonth());
            }}
            className="ml-1 rounded-md border border-zinc-300 px-2.5 py-1 text-xs hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
          >
            오늘
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs">
          <select
            value={filterCategory}
            onChange={(e) => setFilterCategory(e.target.value)}
            className={selectCls}
          >
            <option value="전체">분류 — 전체</option>
            <option value="외근">외근</option>
            <option value="출장">출장</option>
            <option value="휴가">휴가</option>
          </select>
          <select
            value={filterAssignee}
            onChange={(e) => setFilterAssignee(e.target.value)}
            className={selectCls}
          >
            <option value="전체">직원 — 전체</option>
            {allAssignees.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </div>
      </div>

      {error && (
        <div className="rounded-md border border-red-500/40 bg-red-500/5 p-3 text-sm text-red-400">
          {error instanceof Error ? error.message : String(error)}
        </div>
      )}

      {isLoading && !data ? (
        <LoadingState message="일정 불러오는 중" height="h-96" />
      ) : (
        <div className="overflow-hidden rounded-xl border border-zinc-200 dark:border-zinc-800">
          {/* 요일 헤더 */}
          <div className="grid grid-cols-7 border-b border-zinc-200 bg-zinc-50 text-center text-[11px] font-medium text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
            {["일", "월", "화", "수", "목", "금", "토"].map((d, i) => (
              <div
                key={d}
                className={cn(
                  "py-1.5",
                  i === 0 && "text-red-500",
                  i === 6 && "text-blue-500",
                )}
              >
                {d}
              </div>
            ))}
          </div>
          <div className="grid grid-cols-7">
            {cells.map((c) => {
              const items = taskByDay.get(c.key) ?? [];
              const isCurMonth = c.date.getMonth() === month;
              const isToday = c.key === todayKey;
              const dayOfWeek = c.date.getDay();
              return (
                <div
                  key={c.key}
                  className={cn(
                    "min-h-[110px] border-b border-r border-zinc-200 p-1 text-[11px] dark:border-zinc-800",
                    !isCurMonth && "bg-zinc-50/40 text-zinc-400 dark:bg-zinc-950/40",
                    isToday && "ring-1 ring-inset ring-blue-500",
                  )}
                >
                  <div
                    className={cn(
                      "mb-0.5 text-right font-medium",
                      dayOfWeek === 0 && "text-red-500",
                      dayOfWeek === 6 && "text-blue-500",
                    )}
                  >
                    {c.date.getDate()}
                  </div>
                  <ul className="space-y-0.5">
                    {items.slice(0, 4).map((t) => (
                      <li key={`${c.key}:${t.id}`}>
                        <button
                          type="button"
                          onClick={() => setEditing(t)}
                          className={cn(
                            "block w-full truncate rounded px-1 py-0.5 text-left text-[10px]",
                            categoryBg(t),
                          )}
                          title={`${t.assignees.join(", ")} · ${t.title}`}
                        >
                          {t.assignees[0] ? `${t.assignees[0]} ` : ""}
                          {scheduleLabel(t)}
                        </button>
                      </li>
                    ))}
                    {items.length > 4 && (
                      <li className="px-1 text-[10px] text-zinc-400">
                        +{items.length - 4}건
                      </li>
                    )}
                  </ul>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <p className="text-[11px] text-zinc-500">
        총 {filtered.length}건 표시 (전체 {allItems.length}건). 카드 클릭 시 상세 편집.
      </p>

      <TaskEditModal
        task={editing}
        onClose={() => setEditing(null)}
        onSaved={() => setEditing(null)}
      />
    </div>
  );
}

const navBtn =
  "rounded-md border border-zinc-300 px-2.5 py-1 text-sm hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800";
const selectCls =
  "rounded-md border border-zinc-300 bg-white px-2.5 py-1 text-xs outline-none dark:border-zinc-700 dark:bg-zinc-950";

function categoryBg(t: Task): string {
  // 분류 우선, 없으면 활동
  const tag = t.category || t.activity;
  switch (tag) {
    case "외근":
      return "bg-orange-500/15 text-orange-700 dark:text-orange-300 hover:bg-orange-500/25";
    case "출장":
      return "bg-red-500/15 text-red-700 dark:text-red-300 hover:bg-red-500/25";
    case "휴가":
      return "bg-pink-500/15 text-pink-700 dark:text-pink-300 hover:bg-pink-500/25";
    default:
      return "bg-zinc-200/60 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300";
  }
}

function scheduleLabel(t: Task): string {
  // 표현:
  //   - 종일(date only): "외근"
  //   - 시작=종료 시각: "09:00 외근"
  //   - 범위: "09:00~13:00 외근"
  const tag = t.category || t.activity || "일정";
  const startIso = t.start_date;
  const endIso = t.end_date;
  if (startIso && startIso.includes("T")) {
    const s = formatHm(startIso);
    const e = endIso && endIso.includes("T") ? formatHm(endIso) : "";
    if (s && e && s !== e) return `${s}~${e} ${tag}`;
    if (s) return `${s} ${tag}`;
  }
  return tag;
}

function formatHm(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return new Intl.DateTimeFormat("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Seoul",
  }).format(d);
}

function buildMonthGrid(
  year: number,
  month: number,
): Array<{ date: Date; key: string }> {
  // 그 달 1일이 속한 주의 일요일부터 6주(42칸)
  const first = new Date(year, month, 1);
  const startOfWeek = new Date(first);
  startOfWeek.setDate(first.getDate() - first.getDay());
  const cells: Array<{ date: Date; key: string }> = [];
  for (let i = 0; i < 42; i++) {
    const d = new Date(
      startOfWeek.getFullYear(),
      startOfWeek.getMonth(),
      startOfWeek.getDate() + i,
    );
    cells.push({ date: d, key: ymdString(d) });
  }
  return cells;
}

function ymdString(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function isoToYmd(s: string | null): string | null {
  if (!s) return null;
  return s.slice(0, 10);
}

function ymdToDate(s: string): Date {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function navigate(
  year: number,
  month: number,
  delta: number,
  setYear: (y: number) => void,
  setMonth: (m: number) => void,
): void {
  let m = month + delta;
  let y = year;
  while (m < 0) {
    m += 12;
    y -= 1;
  }
  while (m > 11) {
    m -= 12;
    y += 1;
  }
  setYear(y);
  setMonth(m);
}
