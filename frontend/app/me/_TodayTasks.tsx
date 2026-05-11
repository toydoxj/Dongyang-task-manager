"use client";

/**
 * /me 페이지 — 오늘의 할 일 / 일정 카드 view.
 * scope="todo": 프로젝트 + 미분류 그리드
 * scope="schedule": 외근/출장/파견/휴가 4-col
 *
 * PR-AM — app/me/page.tsx에서 추출 (외과적 변경 / 동작 동일).
 */

import type { Project, Task } from "@/lib/domain";

import { CategoryCard, ProjectTaskList, TaskCard } from "./_taskParts";
import { normId } from "./_utils";

export type TodayTasksScope = "todo" | "schedule";

interface Props {
  tasks: Task[];
  projects: Project[];
  onClickTask: (t: Task) => void;
  onDeleteTask: (t: Task) => void;
  /** 휴가 카드 + 버튼 클릭. 부모가 setTaskCreate({ category: '휴가(연차)' }) 처리. */
  onAddVacation?: () => void;
  /** "todo"=프로젝트+미분류, "schedule"=외근/출장/휴가 카드만. */
  scope: TodayTasksScope;
}

export default function TodayTasks({
  tasks,
  projects,
  onClickTask,
  onDeleteTask,
  onAddVacation,
  scope,
}: Props) {
  const open = tasks.filter((t) => t.status !== "완료");
  open.sort((a, b) => {
    if (!a.end_date && !b.end_date) return 0;
    if (!a.end_date) return 1;
    if (!b.end_date) return -1;
    return a.end_date.localeCompare(b.end_date);
  });

  if (open.length === 0) {
    return (
      <p className="rounded-md border border-zinc-200 bg-white p-4 text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900">
        오늘 처리할 업무가 없습니다. 🎉
      </p>
    );
  }

  // project_id → name lookup (id에 dash 유무 차이 무시)
  const projectByNorm = new Map<string, Project>();
  for (const p of projects) {
    projectByNorm.set(normId(p.id), p);
  }
  const findProject = (pid: string | undefined): Project | undefined =>
    pid ? projectByNorm.get(normId(pid)) : undefined;

  // 1) 프로젝트 분류 → 상단 2열 grid
  // 2) 미분류 → amber 영역
  // 3) 기타 업무(개인업무/사내잡무/교육/서비스) → status별 4열 카드
  // 4) 일정 → 3열 카드 (분류=외근/출장/휴가 OR 활동=외근/출장 인 task 모두)
  //    - 프로젝트 task가 활동=외근이면 일정에도 함께 노출
  // '서비스' 는 옛 표기 (새 옵션은 '영업(서비스)'). 데이터 호환을 위해 둘 다 포함.
  const NON_PROJECT_WORK = [
    "개인업무",
    "사내잡무",
    "교육",
    "서비스",
    "영업(서비스)",
  ];
  const STATUSES = ["시작 전", "진행 중", "완료", "보류"] as const;

  const projectTasks: Task[] = [];
  const otherByStatus = new Map<string, Task[]>();
  for (const s of STATUSES) otherByStatus.set(s, []);
  const scheduleByBucket = new Map<string, Task[]>([
    ["외근", []],
    ["출장", []],
    ["파견", []],
    ["휴가", []],
  ]);
  const unclassified: Task[] = [];

  // 휴가는 옛 표기('휴가')와 새 표기('휴가(연차)') 모두 같은 일정 버킷으로 처리
  const isVacationCat = (c: string): boolean => c === "휴가" || c === "휴가(연차)";

  for (const t of open) {
    // 일정 영역에 등장해야 하는가 (분류 또는 활동 기준)
    const scheduleBucket =
      isVacationCat(t.category)
        ? "휴가"
        : t.activity === "파견" || t.category === "파견"
          ? "파견"
          : t.activity === "출장" || t.category === "출장"
            ? "출장"
            : t.activity === "외근" || t.category === "외근"
              ? "외근"
              : null;
    if (scheduleBucket) {
      scheduleByBucket.get(scheduleBucket)!.push(t);
    }

    // 메인 그룹 (프로젝트/기타/미분류) — 일정 분류는 메인에서 제외, 단 프로젝트 분류는 일정과 별개로 메인에 둠
    if (t.category === "프로젝트") {
      projectTasks.push(t);
    } else if (NON_PROJECT_WORK.includes(t.category)) {
      const bucket = otherByStatus.get(t.status) ?? otherByStatus.get("시작 전")!;
      bucket.push(t);
    } else if (
      t.category === "외근" ||
      t.category === "출장" ||
      t.category === "파견" ||
      isVacationCat(t.category)
    ) {
      // 일정 분류 task는 메인 영역에 추가 안 함 (일정 카드에만 표시)
    } else {
      unclassified.push(t);
    }
  }

  const todoCount = projectTasks.length + unclassified.length;

  if (scope === "todo") {
    return (
      <div className="space-y-5">
        {projectTasks.length > 0 && (
          <ProjectTaskList
            items={projectTasks}
            findProject={findProject}
            onClickTask={onClickTask}
            onDeleteTask={onDeleteTask}
          />
        )}

        {unclassified.length > 0 && (
          <div>
            <h3 className="mb-1.5 flex items-center gap-2 text-xs font-medium text-amber-600 dark:text-amber-400">
              <span>미분류 — 분류를 지정해 주세요</span>
              <span className="text-zinc-400">({unclassified.length})</span>
            </h3>
            <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {unclassified.map((t) => (
                <TaskCard
                  key={t.id}
                  task={t}
                  project={findProject(t.project_ids[0])}
                  onClick={() => onClickTask(t)}
                  onDelete={() => onDeleteTask(t)}
                  warn
                />
              ))}
            </ul>
          </div>
        )}

        {todoCount === 0 && (
          <p className="rounded-md border border-zinc-200 bg-white p-4 text-center text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900">
            할 일이 없습니다.
          </p>
        )}
      </div>
    );
  }

  // scope === "schedule"
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {(["외근", "출장", "파견", "휴가"] as const).map((c) => (
        <CategoryCard
          key={c}
          label={c}
          items={scheduleByBucket.get(c) ?? []}
          onClickTask={onClickTask}
          showTime
          showProjectBadge
          findProject={findProject}
          onAdd={c === "휴가" ? onAddVacation : undefined}
          addLabel={c === "휴가" ? "+ 새 휴가" : undefined}
        />
      ))}
    </div>
  );
}
