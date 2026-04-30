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

import { useAuth } from "@/components/AuthGuard";
import TaskEditModal from "@/components/project/TaskEditModal";
import LoadingState from "@/components/ui/LoadingState";
import type { Task } from "@/lib/domain";
import { useTasks } from "@/lib/hooks";

export default function SchedulePage() {
  const { user } = useAuth();
  const [editing, setEditing] = useState<Task | null>(null);
  const { data, error, isLoading } = useTasks(
    { schedule_only: true },
    Boolean(user),
  );
  const items = useMemo(() => data?.items ?? [], [data]);

  const events = useMemo(
    () =>
      items
        .map((t) => taskToEvent(t))
        .filter((e): e is FCEvent => e !== null),
    [items],
  );

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">직원 일정</h1>
          <p className="mt-1 text-sm text-zinc-500">
            외근·출장·휴가 일정. 일정 클릭으로 편집. NAVER WORKS Calendar
            공유 캘린더에 자동 동기화됩니다.
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

      <p className="text-[11px] text-zinc-500">
        총 {items.length}건. 일정 등록·수정·삭제는 항상 task.dyce.kr에서.
        NAVER WORKS Calendar에서 직접 수정한 내용은 동기화되지 않습니다.
      </p>

      <TaskEditModal
        task={editing}
        onClose={() => setEditing(null)}
        onSaved={() => setEditing(null)}
      />
    </div>
  );
}

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
