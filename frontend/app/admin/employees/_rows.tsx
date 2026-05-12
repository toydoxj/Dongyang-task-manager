"use client";

/**
 * /admin/employees 페이지 row 컴포넌트 + cell/input class 상수.
 * - SortableRow: 표시 모드 row (dnd handle + 편집/퇴사/복직/삭제 버튼)
 * - EditRow: inline edit
 * - NewRow: 새 직원 추가
 *
 * PR-AX — app/admin/employees/page.tsx에서 추출 (외과적 변경 / 동작 동일).
 */

import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useState } from "react";

import { createEmployee, updateEmployee } from "@/lib/api";
import type { Employee, EmployeeCreate } from "@/lib/domain";
import { cn } from "@/lib/utils";

export const cellCls = "px-3 py-2 align-top";
export const inputCls =
  "w-full rounded border border-zinc-300 bg-white px-2 py-1 text-xs dark:border-zinc-700 dark:bg-zinc-950";

export function SortableRow({
  emp,
  dndEnabled,
  onEdit,
  onDelete,
  onResign,
  onRestore,
}: {
  emp: Employee;
  dndEnabled: boolean;
  onEdit: () => void;
  onDelete: () => void;
  onResign: () => void;
  onRestore: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: emp.id, disabled: !dndEnabled });
  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };
  const resigned = !!emp.resigned_at;
  return (
    <tr
      ref={setNodeRef}
      style={style}
      className={cn(
        "border-t border-zinc-200 hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900",
        resigned && "text-zinc-400 dark:text-zinc-500",
      )}
    >
      <td className="w-8 px-2 py-2 text-center">
        {dndEnabled ? (
          <button
            type="button"
            {...attributes}
            {...listeners}
            className="cursor-grab text-zinc-400 hover:text-zinc-700 active:cursor-grabbing dark:hover:text-zinc-200"
            title="드래그로 순서 변경"
            aria-label="드래그 핸들"
          >
            ⋮⋮
          </button>
        ) : null}
      </td>
      <td className={cellCls}>{emp.name}</td>
      <td className={cellCls}>{emp.position || "—"}</td>
      <td className={cellCls}>{emp.team || "—"}</td>
      <td className={cellCls}>{emp.degree || "—"}</td>
      <td className={cellCls}>{emp.license || "—"}</td>
      <td className={cellCls}>{emp.grade || "—"}</td>
      <td className={cn(cellCls, "text-zinc-500")}>{emp.email || "—"}</td>
      <td className={cellCls}>
        {emp.linked_user_id ? (
          <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] text-emerald-500">
            연결됨
          </span>
        ) : (
          <span className="text-[10px] text-zinc-500">미연결</span>
        )}
      </td>
      <td className={cellCls}>
        {emp.resigned_at ? (
          <span className="rounded bg-zinc-500/15 px-1.5 py-0.5 text-[10px] text-zinc-500">
            {emp.resigned_at}
          </span>
        ) : (
          <span className="text-[10px] text-zinc-400">—</span>
        )}
      </td>
      <td className={cn(cellCls, "text-right whitespace-nowrap")}>
        <button
          type="button"
          onClick={onEdit}
          className="rounded border border-zinc-300 px-2 py-0.5 text-[11px] hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
        >
          편집
        </button>
        {resigned ? (
          <button
            type="button"
            onClick={onRestore}
            className="ml-1 rounded border border-emerald-300 px-2 py-0.5 text-[11px] text-emerald-600 hover:bg-emerald-50 dark:border-emerald-900 dark:hover:bg-emerald-950"
          >
            복직
          </button>
        ) : (
          <button
            type="button"
            onClick={onResign}
            className="ml-1 rounded border border-amber-300 px-2 py-0.5 text-[11px] text-amber-600 hover:bg-amber-50 dark:border-amber-900 dark:hover:bg-amber-950"
          >
            퇴사
          </button>
        )}
        <button
          type="button"
          onClick={onDelete}
          className="ml-1 rounded border border-red-300 px-2 py-0.5 text-[11px] text-red-500 hover:bg-red-50 dark:border-red-900 dark:hover:bg-red-950"
        >
          삭제
        </button>
      </td>
    </tr>
  );
}

export function EditRow({
  emp,
  onSaved,
  onCancel,
  onError,
}: {
  emp: Employee;
  onSaved: () => void;
  onCancel: () => void;
  onError: (msg: string) => void;
}) {
  const [form, setForm] = useState({
    name: emp.name,
    position: emp.position,
    team: emp.team,
    degree: emp.degree,
    license: emp.license,
    grade: emp.grade,
    email: emp.email,
  });
  const [saving, setSaving] = useState(false);

  async function save() {
    if (!form.name.trim()) {
      onError("이름은 필수");
      return;
    }
    setSaving(true);
    try {
      await updateEmployee(emp.id, form);
      onSaved();
    } catch (e) {
      onError(e instanceof Error ? e.message : "저장 실패");
    } finally {
      setSaving(false);
    }
  }

  return (
    <tr className="border-t border-zinc-200 bg-blue-500/5 dark:border-zinc-800">
      <td className="w-8 px-2 py-2" />
      {(
        ["name", "position", "team", "degree", "license", "grade", "email"] as const
      ).map((k) => (
        <td key={k} className={cellCls}>
          <input
            value={form[k]}
            onChange={(e) => setForm((f) => ({ ...f, [k]: e.target.value }))}
            className={inputCls}
          />
        </td>
      ))}
      <td className={cellCls}>—</td>
      <td className={cellCls}>—</td>
      <td className={cn(cellCls, "text-right")}>
        <button
          type="button"
          onClick={() => void save()}
          disabled={saving}
          className="rounded bg-blue-600 px-2 py-0.5 text-[11px] text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {saving ? "..." : "저장"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={saving}
          className="ml-1 rounded border border-zinc-300 px-2 py-0.5 text-[11px] hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
        >
          취소
        </button>
      </td>
    </tr>
  );
}

export function NewRow({
  onSaved,
  onCancel,
  onError,
}: {
  onSaved: () => void;
  onCancel: () => void;
  onError: (msg: string) => void;
}) {
  const [form, setForm] = useState<EmployeeCreate>({
    name: "",
    position: "",
    team: "",
    degree: "",
    license: "",
    grade: "",
    email: "",
  });
  const [saving, setSaving] = useState(false);

  async function save() {
    if (!form.name.trim()) {
      onError("이름은 필수");
      return;
    }
    setSaving(true);
    try {
      await createEmployee(form);
      onSaved();
    } catch (e) {
      onError(e instanceof Error ? e.message : "추가 실패");
    } finally {
      setSaving(false);
    }
  }

  return (
    <tr className="border-t border-zinc-200 bg-emerald-500/5 dark:border-zinc-800">
      <td className="w-8 px-2 py-2" />
      {(
        ["name", "position", "team", "degree", "license", "grade", "email"] as const
      ).map((k) => (
        <td key={k} className={cellCls}>
          <input
            value={form[k] ?? ""}
            placeholder={k === "name" ? "이름*" : ""}
            onChange={(e) => setForm((f) => ({ ...f, [k]: e.target.value }))}
            className={inputCls}
          />
        </td>
      ))}
      <td className={cellCls}>—</td>
      <td className={cellCls}>—</td>
      <td className={cn(cellCls, "text-right")}>
        <button
          type="button"
          onClick={() => void save()}
          disabled={saving}
          className="rounded bg-emerald-600 px-2 py-0.5 text-[11px] text-white hover:bg-emerald-700 disabled:opacity-50"
        >
          {saving ? "..." : "추가"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={saving}
          className="ml-1 rounded border border-zinc-300 px-2 py-0.5 text-[11px] hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
        >
          취소
        </button>
      </td>
    </tr>
  );
}
