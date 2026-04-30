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

      {/* FullCalendar 폰트 미세 조정 — default가 약간 큼 */}
      <style>{`
        .schedule-calendar .fc { font-size: 0.82rem; }
        .schedule-calendar .fc-toolbar-title { font-size: 1.05rem; }
        .schedule-calendar .fc-button { font-size: 0.78rem; padding: 0.25rem 0.55rem; }
        .schedule-calendar .fc-col-header-cell-cushion,
        .schedule-calendar .fc-daygrid-day-number { font-size: 0.78rem; }
        .schedule-calendar .fc-event-title,
        .schedule-calendar .fc-event-time { font-size: 0.72rem; }
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
  switch (tag) {
    case "외근":
      return "#f97316"; // orange-500
    case "출장":
      return "#ef4444"; // red-500
    case "휴가":
      return "#ec4899"; // pink-500
    default:
      return "#71717a"; // zinc-500
  }
}
