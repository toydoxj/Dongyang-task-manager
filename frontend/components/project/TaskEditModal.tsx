"use client";

import { useMemo, useState } from "react";

import { useAuth } from "@/components/AuthGuard";
import Modal from "@/components/ui/Modal";
import { archiveTask, assignMe, updateProject, updateTask } from "@/lib/api";
import type { Project, Task } from "@/lib/domain";
import {
  ACTIVITY_TYPES,
  isTimeBasedTask,
  TASK_CATEGORIES,
  TASK_DIFFICULTIES,
  TASK_PRIORITIES,
  TASK_STATUSES,
} from "@/lib/domain";
import { useProjects } from "@/lib/hooks";
import { cn } from "@/lib/utils";

interface Props {
  task: Task | null;
  onClose: () => void;
  onSaved: () => void;
}

export default function TaskEditModal({ task, onClose, onSaved }: Props) {
  if (!task) return null;
  // task 가 바뀔 때마다 새로 마운트 (useEffect setState 회피)
  return (
    <Form key={task.id} task={task} onClose={onClose} onSaved={onSaved} />
  );
}

function Form({
  task,
  onClose,
  onSaved,
}: {
  task: Task;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [title, setTitle] = useState(task.title ?? "");
  const [status, setStatus] = useState(task.status || "시작 전");
  // datetime-local input은 'YYYY-MM-DDTHH:mm' (timezone 없는 wall clock).
  // 노션은 UTC ISO('+00:00' 또는 'Z')로 저장하므로 KST로 변환 후 잘라야 한다.
  // (변환 없이 slice만 하면 UTC 00:00 → input에 12 AM으로 표시되는 버그)
  const normalizeForInput = (s: string | null): string => {
    if (!s) return "";
    if (!s.includes("T")) return s;
    const d = new Date(s);
    if (Number.isNaN(d.getTime())) return s.slice(0, 16);
    const kstMs = d.getTime() + 9 * 60 * 60 * 1000;
    return new Date(kstMs).toISOString().slice(0, 16);
  };
  const [start, setStart] = useState(normalizeForInput(task.start_date));
  const [end, setEnd] = useState(normalizeForInput(task.end_date));
  const [actualEnd, setActualEnd] = useState(task.actual_end_date ?? "");
  const [priority, setPriority] = useState(task.priority ?? "");
  const [difficulty, setDifficulty] = useState(task.difficulty ?? "");
  const [category, setCategory] = useState(task.category ?? "");
  const [activity, setActivity] = useState(task.activity ?? "");
  const [assignees, setAssignees] = useState(task.assignees.join(", "));
  const [note, setNote] = useState(task.note ?? "");
  const [projectId, setProjectId] = useState(task.project_ids[0] ?? "");
  // 사용자가 검색→클릭한 프로젝트의 정보를 별도 cache —
  // 검색 input 비운 후 SWR allData가 사라져도 칩이 즉시 표시되도록.
  const [pickedProjectCache, setPickedProjectCache] = useState<Project | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isTimeBased = isTimeBasedTask(category, activity);
  const { user } = useAuth();
  const myName = user?.name ?? "";
  // 일반직원은 본인 담당 task만 수정 가능 — 비-담당이면 read-only.
  const canEdit =
    user?.role === "admin" ||
    user?.role === "team_lead" ||
    (!!myName && task.assignees.includes(myName));
  // dropdown 기준 사람 = task의 담당자(첫 명). 비어있으면 본인.
  const firstAssignee = useMemo(() => {
    const names = assignees
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    return names[0] ?? myName;
  }, [assignees, myName]);
  // 그 담당자 진행중+대기 프로젝트 — dropdown용 (빠름)
  const { data: mineData } = useProjects(
    firstAssignee ? { assignee: firstAssignee } : undefined,
    category === "프로젝트" && Boolean(firstAssignee),
  );
  // 검색 모드: 전체 (1500+ 첫 호출만 5~15초). 검색 시에만 fetch.
  const [projectQuery, setProjectQuery] = useState("");
  const trimmedQ = projectQuery.trim();
  const searchMode = trimmedQ.length > 0;
  const { data: allData } = useProjects(
    undefined,
    category === "프로젝트" && searchMode,
  );
  const candidates = useMemo<Project[]>(() => {
    if (searchMode) {
      if (!allData) return [];
      const q = trimmedQ.toLowerCase();
      return allData.items
        .filter((p) => `${p.code} ${p.name}`.toLowerCase().includes(q))
        .slice(0, 30);
    }
    if (!mineData) return [];
    // 진행중 + 대기만, 완료/타절/종결/이관 제외
    return mineData.items.filter(
      (p) =>
        !p.completed && (p.stage === "진행중" || p.stage === "대기"),
    );
  }, [searchMode, mineData, allData, trimmedQ]);
  // 현재 선택된 프로젝트의 표시 라벨 — 클릭한 cache 우선 → mine → 검색 list 순.
  const selectedProject = useMemo<Project | null>(() => {
    if (!projectId) return null;
    if (pickedProjectCache?.id === projectId) return pickedProjectCache;
    const fromMine = mineData?.items.find((p) => p.id === projectId);
    if (fromMine) return fromMine;
    const fromAll = allData?.items.find((p) => p.id === projectId);
    return fromAll ?? null;
  }, [projectId, pickedProjectCache, mineData, allData]);

  const handlePickProject = async (p: Project): Promise<void> => {
    if (busy) return;
    // 담당자 기준 — 그 사람이 미담당이면 assignMe 호출 (본인이면 그냥, 다른 사람이면 forUser)
    const targetName = firstAssignee;
    const alreadyAssigned =
      targetName && p.assignees.includes(targetName);
    if (!alreadyAssigned && targetName) {
      // 프로젝트 진행단계가 "진행중"이 아니고 task 상태가 "시작 전"이면 → "대기"
      // (assignMe의 setToWaiting=true 사용)
      // task 상태가 "진행 중"이면 → 별도 updateProject로 "진행중"
      // 그 외엔 진행단계 변경 없이 담당자만 추가
      const needSetWaiting =
        p.stage !== "진행중" && status === "시작 전";
      const needSetActive =
        p.stage !== "진행중" && status === "진행 중";
      setBusy(true);
      try {
        const forUser = targetName !== myName ? targetName : undefined;
        await assignMe(p.id, {
          setToWaiting: needSetWaiting,
          forUser,
        });
        if (needSetActive) {
          // assignMe 후 별도 호출로 "진행중"
          await updateProject(p.id, { stage: "진행중" });
        }
      } catch (e) {
        setError(
          e instanceof Error
            ? e.message
            : "프로젝트 담당 추가 실패 (다른 직원 명의는 admin/팀장만 가능)",
        );
        setBusy(false);
        return;
      }
      setBusy(false);
    }
    setProjectId(p.id);
    setPickedProjectCache(p);
    setProjectQuery("");
  };

  const syncDateTimeFormat = (wasTime: boolean, nowTime: boolean): void => {
    if (wasTime === nowTime) return;
    if (nowTime) {
      if (start && !start.includes("T")) setStart(`${start}T09:00`);
      if (end && !end.includes("T")) setEnd(`${end}T18:00`);
    } else {
      if (start.includes("T")) setStart(start.slice(0, 10));
      if (end.includes("T")) setEnd(end.slice(0, 10));
    }
  };

  const onChangeCategory = (next: string): void => {
    syncDateTimeFormat(
      isTimeBasedTask(category, activity),
      isTimeBasedTask(next, activity),
    );
    setCategory(next);
  };
  const onChangeActivity = (next: string): void => {
    syncDateTimeFormat(
      isTimeBasedTask(category, activity),
      isTimeBasedTask(category, next),
    );
    setActivity(next);
  };

  const save = async (): Promise<void> => {
    setBusy(true);
    setError(null);
    try {
      // 빈 문자열은 명시적 'clear' 신호로 backend에 그대로 전송 (None 처리).
      // 원본과 동일하면 변경 없음으로 undefined.
      const wasStart = task.start_date ?? "";
      const wasEnd = task.end_date ?? "";
      const wasActual = task.actual_end_date ?? "";
      const wasPriority = task.priority ?? "";
      const wasDifficulty = task.difficulty ?? "";
      const wasCategory = task.category ?? "";
      const wasActivity = task.activity ?? "";
      const wasProjectId = task.project_ids[0] ?? "";
      // 분류=프로젝트면 project_ids 동기화. 분류가 프로젝트가 아니면 비우기.
      let projectIdsParam: string[] | undefined;
      if (category === "프로젝트") {
        if (projectId !== wasProjectId) {
          projectIdsParam = projectId ? [projectId] : [];
        }
      } else if (wasProjectId) {
        // 분류가 프로젝트에서 다른 것으로 바뀌었으면 relation 비우기
        projectIdsParam = [];
      }
      // 휴가는 예상 완료일과 실제 완료일이 동일 — datetime-local의 시간 부분
      // 잘라낸 date-only 값을 actual_end_date로 자동 set (입력란은 숨김).
      const isVacation = category === "휴가(연차)" || category === "휴가";
      const effectiveActual = isVacation ? (end || "").slice(0, 10) : actualEnd;
      await updateTask(task.id, {
        title,
        status,
        start_date: start === wasStart ? undefined : start,
        end_date: end === wasEnd ? undefined : end,
        actual_end_date:
          effectiveActual === wasActual ? undefined : effectiveActual,
        priority: priority === wasPriority ? undefined : priority,
        difficulty: difficulty === wasDifficulty ? undefined : difficulty,
        category: category === wasCategory ? undefined : category,
        activity: activity === wasActivity ? undefined : activity,
        assignees: assignees
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        note,
        project_ids: projectIdsParam,
      });
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "저장 실패");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (): Promise<void> => {
    if (
      !confirm(
        `"${task.title}" 업무를 삭제하시겠습니까?\n노션에서 보관 처리됩니다 (영구 삭제는 노션에서 가능).`,
      )
    )
      return;
    setBusy(true);
    try {
      await archiveTask(task.id);
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "삭제 실패");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={true}
      onClose={onClose}
      title={canEdit ? "업무 TASK 편집" : "업무 TASK (읽기 전용)"}
      size="md"
    >
      <div className="space-y-4">
        {!canEdit && (
          <p className="rounded-md border border-amber-500/40 bg-amber-500/5 p-2 text-xs text-amber-500">
            본인 담당 task가 아니라 읽기 전용입니다.
          </p>
        )}
        <fieldset disabled={!canEdit} className="contents">
        <Field label="제목">
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className={inputCls}
          />
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="상태">
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className={inputCls}
            >
              {TASK_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </Field>
          <Field label="우선순위">
            <select
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
              className={inputCls}
            >
              <option value="">—</option>
              {TASK_PRIORITIES.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </Field>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Field label="분류">
            <select
              value={category}
              onChange={(e) => onChangeCategory(e.target.value)}
              className={inputCls}
            >
              <option value="">— 미분류</option>
              {TASK_CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </Field>
          <Field label="활동">
            <select
              value={activity}
              onChange={(e) => onChangeActivity(e.target.value)}
              className={inputCls}
            >
              <option value="">—</option>
              {ACTIVITY_TYPES.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </Field>
        </div>

        {category === "프로젝트" && (
          <Field label="프로젝트">
            <div className="space-y-2">
              {/* 현재 선택 표시 */}
              {projectId && (
                <div className="flex items-center justify-between rounded-md border border-zinc-200 bg-zinc-50 px-2.5 py-1.5 text-xs dark:border-zinc-700 dark:bg-zinc-800">
                  <span className="truncate">
                    ✓{" "}
                    {selectedProject
                      ? `${selectedProject.code ? `[${selectedProject.code}] ` : ""}${selectedProject.name || "(제목 없음)"}`
                      : "(현재 선택)"}
                  </span>
                  <button
                    type="button"
                    onClick={() => setProjectId("")}
                    className="text-zinc-500 hover:text-red-500"
                    title="선택 해제"
                  >
                    ✕
                  </button>
                </div>
              )}
              {/* 검색 input — 빈 검색이면 담당자 진행중/대기, 검색어 있으면 전체 */}
              <input
                type="search"
                placeholder={`검색어 없으면 ${firstAssignee || "본인"} 담당, 검색하면 전체`}
                value={projectQuery}
                onChange={(e) => setProjectQuery(e.target.value)}
                className={inputCls}
              />
              <div className="max-h-44 divide-y divide-zinc-200 overflow-y-auto rounded-md border border-zinc-200 dark:divide-zinc-800 dark:border-zinc-700">
                {searchMode && !allData && (
                  <p className="p-3 text-center text-[11px] text-zinc-500">
                    전체 프로젝트 불러오는 중 (5~15초)…
                  </p>
                )}
                {!searchMode && !mineData && (
                  <p className="p-3 text-center text-[11px] text-zinc-500">
                    내 담당 프로젝트 불러오는 중…
                  </p>
                )}
                {(searchMode ? allData : mineData) &&
                  candidates.length === 0 && (
                    <p className="p-3 text-center text-[11px] text-zinc-500">
                      {searchMode
                        ? "검색 결과 없음"
                        : `${firstAssignee || "본인"} 담당 진행중·대기 프로젝트 없음 — 검색해서 선택`}
                    </p>
                  )}
                {candidates.map((p) => {
                  const targetAssigned =
                    !!firstAssignee && p.assignees.includes(firstAssignee);
                  const isSelected = p.id === projectId;
                  return (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => handlePickProject(p)}
                      disabled={busy}
                      className={cn(
                        "flex w-full items-center justify-between gap-2 px-2.5 py-1.5 text-left text-xs transition-colors",
                        isSelected
                          ? "bg-blue-50 dark:bg-blue-900/20"
                          : "hover:bg-zinc-50 dark:hover:bg-zinc-800/50",
                        busy && "opacity-50",
                      )}
                    >
                      <span className="min-w-0 flex-1 truncate">
                        {p.code ? `[${p.code}] ` : ""}
                        {p.name || "(제목 없음)"}
                        <span className="ml-1 text-[10px] text-zinc-500">
                          · {p.stage || "—"}
                        </span>
                      </span>
                      <span className="shrink-0 text-[10px] text-zinc-500">
                        {targetAssigned
                          ? `${firstAssignee} 담당`
                          : `+ ${firstAssignee || "본인"} 추가`}
                      </span>
                    </button>
                  );
                })}
              </div>
              <p className="text-[10px] text-zinc-500">
                담당자({firstAssignee || "본인"}) 기준. 미담당 프로젝트 선택 시
                자동으로 담당 추가 — task 상태가 시작 전이면 진행단계 "대기",
                진행 중이면 "진행중"으로 자동 설정.
              </p>
            </div>
          </Field>
        )}

        <Field label="난이도">
          <select
            value={difficulty}
            onChange={(e) => setDifficulty(e.target.value)}
            className={inputCls}
          >
            <option value="">—</option>
            {TASK_DIFFICULTIES.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label={isTimeBased ? "시작 일시" : "시작일"}>
            <input
              type={isTimeBased ? "datetime-local" : "date"}
              value={start}
              onChange={(e) => setStart(e.target.value)}
              className={inputCls}
            />
          </Field>
          <Field label={isTimeBased ? "종료 일시" : "예상 완료일"}>
            <input
              type={isTimeBased ? "datetime-local" : "date"}
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              className={inputCls}
            />
          </Field>
        </div>

        {/* 휴가는 예상 완료일=실제 완료일 정책 — 입력란 숨기고 자동 동기화. */}
        {category !== "휴가(연차)" && category !== "휴가" && (
          <Field label="실제 완료일 (완료 시)">
            <input
              type="date"
              value={actualEnd}
              onChange={(e) => setActualEnd(e.target.value)}
              className={inputCls}
            />
          </Field>
        )}

        <Field label="담당자 (쉼표로 구분)">
          <input
            type="text"
            value={assignees}
            onChange={(e) => setAssignees(e.target.value)}
            placeholder="홍길동, 김철수"
            className={inputCls}
          />
        </Field>

        <Field label="비고">
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={3}
            className={`${inputCls} resize-y`}
          />
        </Field>

        {error && (
          <p className="rounded-md border border-red-500/40 bg-red-500/5 p-2 text-xs text-red-400">
            {error}
          </p>
        )}
        </fieldset>

        <footer className="flex items-center justify-between gap-2 pt-2">
          {canEdit ? (
            <button
              type="button"
              onClick={remove}
              disabled={busy}
              className="text-xs text-red-500 hover:underline disabled:opacity-50"
              title="노션에서 보관 처리됩니다"
            >
              삭제
            </button>
          ) : (
            <span />
          )}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={busy}
              className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
            >
              {canEdit ? "취소" : "닫기"}
            </button>
            {canEdit && (
              <button
                type="button"
                onClick={save}
                disabled={busy}
                className="rounded-md bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
              >
                {busy ? "저장 중..." : "저장"}
              </button>
            )}
          </div>
        </footer>
      </div>
    </Modal>
  );
}

const inputCls =
  "w-full rounded-md border border-zinc-300 bg-white px-2.5 py-1.5 text-sm outline-none focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-950";

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-zinc-500">{label}</span>
      {children}
    </label>
  );
}
