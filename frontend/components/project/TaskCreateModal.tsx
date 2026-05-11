"use client";

import { useState } from "react";

import { useMemo } from "react";

import Modal from "@/components/ui/Modal";
import { useAuth } from "@/components/AuthGuard";
import { createTask } from "@/lib/api";
import type { Project, Sale } from "@/lib/domain";
import {
  ACTIVITY_TYPES,
  isTimeBasedTask,
  TASK_CATEGORIES,
  TASK_DIFFICULTIES,
  TASK_PRIORITIES,
  TASK_STATUSES,
} from "@/lib/domain";
import { useSales } from "@/lib/hooks";
import { cn } from "@/lib/utils";

interface Props {
  open: boolean;
  /** 프로젝트 컨텍스트가 정해진 호출(프로젝트 상세 등). 없으면 선택 dropdown 노출. */
  projectId?: string;
  /** 영업 컨텍스트가 정해진 호출(/me 영업 row → + 추가). 분류 자동 '영업(서비스)'. */
  saleId?: string;
  /** 비프로젝트 모드일 때 사용자가 고를 수 있는 프로젝트 목록 (담당 프로젝트 등). */
  projects?: Project[];
  /** 담당자 default. 미지정 시 현재 로그인 사용자. (직원 업무 모드에서 직원 이름 전달) */
  defaultAssignee?: string;
  initialStatus?: string;
  /** 시작일 prefill (schedule grid에서 빈 날짜 클릭 시). YYYY-MM-DD. */
  initialStartDate?: string;
  /** 분류 prefill (schedule context면 '외근' 등). */
  initialCategory?: string;
  onClose: () => void;
  onCreated: () => void;
}

export default function TaskCreateModal({
  open,
  projectId = "",
  saleId = "",
  projects,
  defaultAssignee,
  initialStatus,
  initialStartDate,
  initialCategory,
  onClose,
  onCreated,
}: Props) {
  if (!open) return null;
  return (
    <Form
      key={`${projectId}:${saleId}:${initialStatus ?? ""}:${initialStartDate ?? ""}:${initialCategory ?? ""}`}
      projectId={projectId}
      saleId={saleId}
      projects={projects}
      defaultAssignee={defaultAssignee}
      initialStatus={initialStatus}
      initialStartDate={initialStartDate}
      initialCategory={initialCategory}
      onClose={onClose}
      onCreated={onCreated}
    />
  );
}

function Form({
  projectId,
  saleId,
  projects,
  defaultAssignee,
  initialStatus,
  initialStartDate,
  initialCategory,
  onClose,
  onCreated,
}: {
  projectId: string;
  saleId: string;
  projects?: Project[];
  defaultAssignee?: string;
  initialStatus?: string;
  initialStartDate?: string;
  initialCategory?: string;
  onClose: () => void;
  onCreated: () => void;
}) {
  const { user } = useAuth();
  const today = new Date().toISOString().slice(0, 10);
  const [title, setTitle] = useState("");
  const [status, setStatus] = useState(initialStatus || "시작 전");
  // 첫 mount 시 prefill 형식을 분류와 일치 — time-based(외근/출장)면 T09:00,
  // date-based(휴가/프로젝트 등)면 date only. input type과 일치해야 표시됨.
  // saleId 있으면 분류 자동 '영업(서비스)' (initialCategory 미지정 시).
  const initialCat = projectId
    ? "프로젝트"
    : saleId
      ? "영업(서비스)"
      : initialCategory || "";
  const initialIsTime = isTimeBasedTask(initialCat, "");
  const baseDate = initialStartDate || today;
  const startDefault =
    initialIsTime && !baseDate.includes("T") ? `${baseDate}T09:00` : baseDate;
  const endDefault = !initialStartDate
    ? ""
    : initialIsTime && !initialStartDate.includes("T")
      ? `${initialStartDate}T18:00`
      : initialStartDate;
  const [start, setStart] = useState(startDefault);
  const [end, setEnd] = useState(endDefault);
  const [priority, setPriority] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [category, setCategory] = useState(initialCat);
  const [activity, setActivity] = useState("");
  // 분류=프로젝트 + projectId 미지정인 경우(=/me에서 새 업무) 사용자가 dropdown으로 선택
  const [pickedProjectId, setPickedProjectId] = useState(projectId);
  // 영업(서비스) picker — saleId prop 있으면 prefill (외부 호출 컨텍스트)
  const [pickedSaleId, setPickedSaleId] = useState(saleId);
  const [saleQuery, setSaleQuery] = useState("");
  // 담당자 default: defaultAssignee(직원 업무 모드의 직원 이름) > 본인
  const [assignees, setAssignees] = useState(defaultAssignee ?? user?.name ?? "");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const showProjectPicker = category === "프로젝트" && !projectId;
  const showSalePicker = category === "영업(서비스)";
  const isTimeBased = isTimeBasedTask(category, activity);

  const { data: salesData } = useSales(undefined, showSalePicker);
  const trimmedSaleQ = saleQuery.trim().toLowerCase();
  const saleCandidates = useMemo<Sale[]>(() => {
    if (!salesData) return [];
    const items = salesData.items;
    if (!trimmedSaleQ) return items.slice(0, 50);
    return items
      .filter((s) =>
        `${s.code} ${s.name}`.toLowerCase().includes(trimmedSaleQ),
      )
      .slice(0, 50);
  }, [salesData, trimmedSaleQ]);
  const selectedSale = useMemo<Sale | null>(
    () => salesData?.items.find((s) => s.id === pickedSaleId) ?? null,
    [salesData, pickedSaleId],
  );

  /** 시간 기반 ↔ date 형식 전환 시 input value 변환. */
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

  const submit = async (): Promise<void> => {
    if (!title.trim()) {
      setError("제목을 입력하세요");
      return;
    }
    const finalProjectId = projectId || pickedProjectId;
    if (category === "프로젝트" && !finalProjectId) {
      setError("분류가 '프로젝트'면 프로젝트를 선택하세요");
      return;
    }
    if (category === "영업(서비스)" && !pickedSaleId) {
      setError("분류가 '영업(서비스)'면 영업을 선택하세요");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await createTask({
        title: title.trim(),
        project_id: category === "프로젝트" ? finalProjectId : "",
        sale_id: category === "영업(서비스)" ? pickedSaleId : "",
        category: category || undefined,
        activity: activity || undefined,
        status,
        start_date: start || undefined,
        end_date: end || undefined,
        priority: priority || undefined,
        difficulty: difficulty || undefined,
        assignees: assignees
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        note: note || undefined,
      });
      onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "생성 실패");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={true} onClose={onClose} title="새 업무 TASK" size="md">
      <div className="space-y-3">
        <Field label="제목" required>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className={inputCls}
            placeholder="예: 1차 도면 검토"
            autoFocus
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
              onChange={(e) => {
                const next = e.target.value;
                syncDateTimeFormat(
                  isTimeBasedTask(category, activity),
                  isTimeBasedTask(next, activity),
                );
                setCategory(next);
              }}
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
              onChange={(e) => {
                const next = e.target.value;
                syncDateTimeFormat(
                  isTimeBasedTask(category, activity),
                  isTimeBasedTask(category, next),
                );
                setActivity(next);
              }}
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

        {showProjectPicker && (
          <Field label="프로젝트" required>
            <select
              value={pickedProjectId}
              onChange={(e) => setPickedProjectId(e.target.value)}
              className={inputCls}
            >
              <option value="">— 선택하세요</option>
              {(projects ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.code ? `[${p.code}] ` : ""}{p.name}
                </option>
              ))}
            </select>
          </Field>
        )}

        {showSalePicker && (
          <Field label="영업" required>
            <div className="space-y-2">
              {pickedSaleId && (
                <div className="flex items-center justify-between rounded-md border border-zinc-200 bg-zinc-50 px-2.5 py-1.5 text-xs dark:border-zinc-700 dark:bg-zinc-800">
                  <span className="truncate">
                    ✓{" "}
                    {selectedSale
                      ? `${selectedSale.code ? `[${selectedSale.code}] ` : ""}${selectedSale.name || "(이름 없음)"}`
                      : "(현재 선택)"}
                  </span>
                  <button
                    type="button"
                    onClick={() => setPickedSaleId("")}
                    className="text-zinc-500 hover:text-red-500"
                    title="선택 해제"
                  >
                    ✕
                  </button>
                </div>
              )}
              <input
                type="search"
                placeholder="영업 코드 또는 이름 검색"
                value={saleQuery}
                onChange={(e) => setSaleQuery(e.target.value)}
                className={inputCls}
              />
              <div className="max-h-44 divide-y divide-zinc-200 overflow-y-auto rounded-md border border-zinc-200 dark:divide-zinc-800 dark:border-zinc-700">
                {!salesData && (
                  <p className="p-3 text-center text-[11px] text-zinc-500">
                    영업 목록 불러오는 중…
                  </p>
                )}
                {salesData && saleCandidates.length === 0 && (
                  <p className="p-3 text-center text-[11px] text-zinc-500">
                    {trimmedSaleQ ? "검색 결과 없음" : "등록된 영업 없음"}
                  </p>
                )}
                {saleCandidates.map((s) => {
                  const isSelected = s.id === pickedSaleId;
                  return (
                    <button
                      key={s.id}
                      type="button"
                      onClick={() => {
                        setPickedSaleId(s.id);
                        setSaleQuery("");
                      }}
                      className={cn(
                        "flex w-full items-center justify-between gap-2 px-2.5 py-1.5 text-left text-xs transition-colors",
                        isSelected
                          ? "bg-blue-50 dark:bg-blue-900/20"
                          : "hover:bg-zinc-50 dark:hover:bg-zinc-800/50",
                      )}
                    >
                      <span className="min-w-0 flex-1 truncate">
                        {s.code ? `[${s.code}] ` : ""}
                        {s.name || "(이름 없음)"}
                        <span className="ml-1 text-[10px] text-zinc-500">
                          · {s.stage || "—"}
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          </Field>
        )}

        <div className="grid grid-cols-2 gap-3">
          <Field label={isTimeBased ? "시작 일시" : "시작일"}>
            <input
              type={isTimeBased ? "datetime-local" : "date"}
              value={start}
              onChange={(e) => {
                const v = e.target.value;
                // 완료일이 비어있거나 이전 시작일과 같으면 자동 동기화
                if (!end || end === start) setEnd(v);
                setStart(v);
              }}
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
            rows={2}
            className={`${inputCls} resize-y`}
          />
        </Field>

        {error && (
          <p className="rounded-md border border-red-500/40 bg-red-500/5 p-2 text-xs text-red-400">
            {error}
          </p>
        )}

        <footer className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
          >
            취소
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={busy}
            className="rounded-md bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
          >
            {busy ? "생성 중..." : "생성"}
          </button>
        </footer>
      </div>
    </Modal>
  );
}

const inputCls =
  "w-full rounded-md border border-zinc-300 bg-white px-2.5 py-1.5 text-sm outline-none focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-950";

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-zinc-500">
        {label}
        {required && <span className="ml-1 text-red-500">*</span>}
      </span>
      {children}
    </label>
  );
}
