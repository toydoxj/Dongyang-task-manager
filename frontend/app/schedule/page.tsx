"use client";

/**
 * 직원 일정 — FullCalendar로 월/주/일 뷰. 데이터 source는 노션 task DB
 * (schedule_only filter). 외근/출장/휴가 등록·수정·삭제는 모달에서.
 *
 * 노션에 저장된 일정은 backend가 NAVER WORKS Calendar 회사 공유 캘린더에
 * 자동 동기화 (단방향 — Task_DY가 source of truth).
 */

import { useMemo, useState } from "react";

import dayGridPlugin from "@fullcalendar/daygrid";
import interactionPlugin from "@fullcalendar/interaction";
import FullCalendar from "@fullcalendar/react";
import timeGridPlugin from "@fullcalendar/timegrid";
import koLocale from "@fullcalendar/core/locales/ko";
import useSWR from "swr";

import { useAuth } from "@/components/AuthGuard";
import TaskCreateModal from "@/components/project/TaskCreateModal";
import TaskEditModal from "@/components/project/TaskEditModal";
import LoadingState from "@/components/ui/LoadingState";
import { getEmployeeTeamsMap } from "@/lib/api";
import type { Task } from "@/lib/domain";
import { TEAMS } from "@/lib/domain";
import { useTasks } from "@/lib/hooks";
import { cn } from "@/lib/utils";

export default function SchedulePage() {
  const { user } = useAuth();
  const [editing, setEditing] = useState<Task | null>(null);
  const [creatingDate, setCreatingDate] = useState<string | null>(null);
  const [filterCategory, setFilterCategory] = useState<string>("전체");
  const [filterTeam, setFilterTeam] = useState<string>("전체");
  const [filterAssignee, setFilterAssignee] = useState<string>("전체");

  const { data, error, isLoading, mutate } = useTasks(
    { schedule_only: true },
    Boolean(user),
  );
  const items = useMemo(() => data?.items ?? [], [data]);

  // 직원 이름 → 팀 매핑 (직원 명부 기반)
  const { data: teamsMap } = useSWR(
    user ? ["employee-teams-map"] : null,
    () => getEmployeeTeamsMap(),
  );

  // 직원 목록 (assignees union)
  const allAssignees = useMemo(() => {
    const s = new Set<string>();
    for (const t of items) for (const a of t.assignees) if (a) s.add(a);
    return Array.from(s).sort((a, b) => a.localeCompare(b, "ko"));
  }, [items]);

  const filtered = useMemo(() => {
    return items.filter((t) => {
      if (filterCategory !== "전체") {
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
      if (filterTeam !== "전체") {
        const map = teamsMap ?? {};
        const matchByEmployee = t.assignees.some(
          (a) => map[a] === filterTeam,
        );
        const matchByTaskTeam = t.teams.includes(filterTeam);
        if (!matchByEmployee && !matchByTaskTeam) return false;
      }
      if (filterAssignee !== "전체") {
        if (!t.assignees.includes(filterAssignee)) return false;
      }
      return true;
    });
  }, [items, filterCategory, filterTeam, filterAssignee, teamsMap]);

  const events = useMemo(
    () =>
      filtered
        .map((t) => taskToEvent(t))
        .filter((e): e is FCEvent => e !== null),
    [filtered],
  );

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">직원 일정</h1>
          <p className="mt-1 text-sm text-zinc-500">
            외근·출장·휴가 일정. 빈 날짜 클릭으로 새 일정, 일정 클릭으로 편집.
            NAVER WORKS Calendar 공유 캘린더에 자동 동기화됩니다.
          </p>
        </div>
        <a
          href="https://calendar.worksmobile.com/"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 rounded-md border border-emerald-700/40 bg-emerald-600/10 px-3 py-1.5 text-xs font-medium text-emerald-300 hover:bg-emerald-600/20"
          title="NAVER WORKS Calendar에서 알림 받기"
        >
          🗓️ NAVER WORKS Calendar ↗
        </a>
      </header>

      {/* 필터 바 */}
      <div className="flex flex-wrap items-center gap-2 rounded-md border border-zinc-200 bg-white p-2.5 text-xs dark:border-zinc-800 dark:bg-zinc-900">
        <select
          value={filterCategory}
          onChange={(e) => setFilterCategory(e.target.value)}
          className={cn(selectCls)}
        >
          <option value="전체">분류 — 전체</option>
          <option value="외근">외근</option>
          <option value="출장">출장</option>
          <option value="휴가">휴가</option>
        </select>
        <select
          value={filterTeam}
          onChange={(e) => setFilterTeam(e.target.value)}
          className={cn(selectCls)}
        >
          <option value="전체">팀 — 전체</option>
          {TEAMS.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <select
          value={filterAssignee}
          onChange={(e) => setFilterAssignee(e.target.value)}
          className={cn(selectCls)}
        >
          <option value="전체">직원 — 전체</option>
          {allAssignees.map((a) => (
            <option key={a} value={a}>
              {a}
            </option>
          ))}
        </select>
        <span className="ml-auto text-[10px] text-zinc-500">
          {filtered.length}/{items.length}건 표시
        </span>
      </div>

      {error && (
        <div className="rounded-md border border-red-500/40 bg-red-500/5 p-3 text-sm text-red-400">
          {error instanceof Error ? error.message : String(error)}
        </div>
      )}

      {isLoading && !data ? (
        <LoadingState message="일정 불러오는 중" height="h-96" />
      ) : (
        <div className="schedule-calendar rounded-xl border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900">
          <FullCalendar
            plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
            initialView="dayGridMonth"
            locale={koLocale}
            headerToolbar={{
              left: "prev,next today",
              center: "title",
              right: "dayGridMonth,timeGridWeek,timeGridDay",
            }}
            buttonText={{
              today: "오늘",
              month: "월",
              week: "주",
              day: "일",
            }}
            events={events}
            eventClick={(info) => {
              const task = info.event.extendedProps?.task as
                | Task
                | undefined;
              if (task) setEditing(task);
            }}
            dateClick={(info) => {
              setCreatingDate(info.dateStr);
            }}
            height="auto"
            dayMaxEvents={4}
            firstDay={0}
            weekends
            nowIndicator
            eventTimeFormat={{
              hour: "2-digit",
              minute: "2-digit",
              hour12: false,
            }}
          />
        </div>
      )}

      {/* 참조(_reference/schedule)의 디자인 톤을 FullCalendar에 적용 */}
      <style>{`
        .schedule-calendar .fc {
          font-size: 0.82rem;
          font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }
        .schedule-calendar .fc-toolbar-title { font-size: 1.05rem; font-weight: 700; letter-spacing: -0.3px; }
        .schedule-calendar .fc-button-primary {
          background: #fff;
          color: #475569;
          border: 1px solid #cbd5e1;
          font-size: 0.78rem;
          font-weight: 500;
          padding: 0.3rem 0.7rem;
          border-radius: 6px;
          box-shadow: none;
        }
        .schedule-calendar .fc-button-primary:hover {
          background: #f8fafc;
          color: #0f172a;
          border-color: #94a3b8;
        }
        .schedule-calendar .fc-button-primary:not(:disabled).fc-button-active,
        .schedule-calendar .fc-button-primary:not(:disabled):active {
          background: #8cb943;
          color: #fff;
          border-color: #8cb943;
        }
        .schedule-calendar .fc-button-primary:disabled {
          background: #f1f5f9;
          color: #94a3b8;
          border-color: #e2e8f0;
        }
        .schedule-calendar .fc-col-header-cell {
          background: #f8fafc;
          font-weight: 600;
        }
        .schedule-calendar .fc-col-header-cell-cushion,
        .schedule-calendar .fc-daygrid-day-number {
          font-size: 0.78rem;
          color: #475569;
          padding: 6px 8px;
        }
        .schedule-calendar .fc-day-sat .fc-col-header-cell-cushion,
        .schedule-calendar .fc-day-sat .fc-daygrid-day-number { color: #2563eb; }
        .schedule-calendar .fc-day-sun .fc-col-header-cell-cushion,
        .schedule-calendar .fc-day-sun .fc-daygrid-day-number { color: #dc2626; }
        .schedule-calendar .fc-event {
          border: none;
          border-left: 3px solid currentColor;
          border-radius: 4px;
          padding: 2px 6px;
          background: color-mix(in srgb, currentColor 12%, white);
          color: var(--fc-event-bg-color, #475569);
          box-shadow: 0 1px 2px rgba(0,0,0,0.05);
          transition: transform 0.1s, box-shadow 0.2s;
        }
        .schedule-calendar .fc-event:hover {
          transform: translateY(-1px);
          box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .schedule-calendar .fc-event-title,
        .schedule-calendar .fc-event-time {
          font-size: 0.72rem;
          color: #1f2937;
          font-weight: 500;
        }
        .schedule-calendar .fc-daygrid-event-dot { display: none; }
        .schedule-calendar .fc-daygrid-day-frame { padding: 2px; }
        @media (prefers-color-scheme: dark) {
          .schedule-calendar .fc-button-primary { background: #18181b; color: #d4d4d8; border-color: #3f3f46; }
          .schedule-calendar .fc-button-primary:hover { background: #27272a; color: #fff; border-color: #52525b; }
          .schedule-calendar .fc-col-header-cell { background: #18181b; }
          .schedule-calendar .fc-col-header-cell-cushion,
          .schedule-calendar .fc-daygrid-day-number { color: #a1a1aa; }
          .schedule-calendar .fc-event-title,
          .schedule-calendar .fc-event-time { color: #f4f4f5; }
        }
      `}</style>

      <TaskEditModal
        task={editing}
        onClose={() => setEditing(null)}
        onSaved={() => {
          setEditing(null);
          void mutate();
        }}
      />

      <TaskCreateModal
        open={creatingDate !== null}
        initialStartDate={creatingDate ?? undefined}
        initialCategory="외근"
        onClose={() => setCreatingDate(null)}
        onCreated={() => {
          setCreatingDate(null);
          void mutate();
        }}
      />
    </div>
  );
}

const selectCls =
  "rounded-md border border-zinc-300 bg-white px-2.5 py-1 text-xs outline-none dark:border-zinc-700 dark:bg-zinc-950";

interface FCEvent {
  id: string;
  title: string;
  start: string;
  end?: string;
  allDay: boolean;
  backgroundColor: string;
  borderColor: string;
  extendedProps: { task: Task };
}

function taskToEvent(task: Task): FCEvent | null {
  if (!task.start_date) return null;
  const tag = task.category || task.activity || "일정";
  const names = task.assignees.length > 0 ? task.assignees.join(", ") : "";
  const title = `${names ? names + " — " : ""}${task.title || "(제목 없음)"}`;
  const isAllDay = !task.start_date.includes("T");
  const color = colorFor(tag);
  return {
    id: task.id,
    title,
    start: task.start_date,
    end: task.end_date ?? undefined,
    allDay: isAllDay,
    backgroundColor: color,
    borderColor: color,
    extendedProps: { task },
  };
}

function colorFor(tag: string): string {
  // 참조 (_reference/schedule/style.css) 디자인의 카테고리 컬러 팔레트:
  //   출장=blue, 외근=amber, 휴가=red, 기본=gray
  switch (tag) {
    case "외근":
      return "#f59e0b"; // amber-500
    case "출장":
      return "#0ea5e9"; // sky-500
    case "휴가":
      return "#ef4444"; // red-500
    default:
      return "#64748b"; // slate-500
  }
}
