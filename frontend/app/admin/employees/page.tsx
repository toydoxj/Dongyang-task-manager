"use client";

import {
  closestCenter,
  DndContext,
  type DragEndEvent,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";

import UnauthorizedRedirect from "@/components/UnauthorizedRedirect";
import { useRoleGuard } from "@/lib/useRoleGuard";
import {
  deleteEmployee,
  listEmployees,
  reorderEmployees,
  resignEmployee,
  restoreEmployee,
  uploadEmployees,
} from "@/lib/api";
import type {
  Employee,
  EmployeeImportResult,
  EmployeeView,
} from "@/lib/domain";
import { cn } from "@/lib/utils";

import { EditRow, NewRow, SortableRow } from "./_rows";

export default function EmployeesAdminPage() {
  const { user, allowed: isAdmin } = useRoleGuard(["admin"]);
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [view, setView] = useState<EmployeeView>("active");
  const { data, isLoading, mutate, error } = useSWR(
    isAdmin ? ["employees", view, debouncedQ] : null,
    () => listEmployees(debouncedQ || undefined, view),
  );
  const [editId, setEditId] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [importMsg, setImportMsg] = useState<string | null>(null);
  const [errMsg, setErrMsg] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q.trim()), 250);
    return () => clearTimeout(t);
  }, [q]);

  // hooks (useSensors/useMemo/useState 등) 호출 전 early return 금지 — rules-of-hooks.
  // 권한 체크는 모든 hook 호출 후로 이동 (page-level guard는 layout 또는 router에서 처리 권장).

  async function onUpload(f: File) {
    setUploading(true);
    setErrMsg(null);
    setImportMsg(null);
    try {
      const r: EmployeeImportResult = await uploadEmployees(f);
      setImportMsg(
        `업로드 완료 — 신규 ${r.inserted} / 갱신 ${r.updated} / 변경없음 ${r.skipped} (총 ${r.total_rows}행)`,
      );
      await mutate();
    } catch (e) {
      setErrMsg(e instanceof Error ? e.message : "업로드 실패");
    } finally {
      setUploading(false);
    }
  }

  async function onDelete(id: number) {
    if (!confirm("이 직원을 영구 삭제하시겠습니까? (퇴사 처리만 하려면 '퇴사' 버튼)"))
      return;
    try {
      await deleteEmployee(id);
      await mutate();
    } catch (e) {
      setErrMsg(e instanceof Error ? e.message : "삭제 실패");
    }
  }

  async function onResign(id: number) {
    const today = new Date().toISOString().slice(0, 10);
    const input = prompt("퇴사일 (YYYY-MM-DD)", today);
    if (!input) return;
    try {
      await resignEmployee(id, input);
      await mutate();
    } catch (e) {
      setErrMsg(e instanceof Error ? e.message : "퇴사 처리 실패");
    }
  }

  async function onRestore(id: number) {
    if (!confirm("복직 처리하시겠습니까?")) return;
    try {
      await restoreEmployee(id);
      await mutate();
    } catch (e) {
      setErrMsg(e instanceof Error ? e.message : "복직 실패");
    }
  }

  // DnD — active view + 검색 없음일 때만 활성화 (퇴사자/검색 결과는 정렬 의미 없음)
  const dndEnabled = view === "active" && !debouncedQ;
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
  );
  const items = useMemo(() => data?.items ?? [], [data]);
  const itemIds = useMemo(() => items.map((e) => e.id), [items]);
  // optimistic: 드래그 중에 list 표시 순서 보존
  const [localOrder, setLocalOrder] = useState<Employee[] | null>(null);
  const displayItems = localOrder ?? items;

  async function handleDragEnd(e: DragEndEvent) {
    if (!dndEnabled) return;
    const { active, over } = e;
    if (!over || active.id === over.id) return;
    const oldIdx = items.findIndex((it) => it.id === Number(active.id));
    const newIdx = items.findIndex((it) => it.id === Number(over.id));
    if (oldIdx < 0 || newIdx < 0) return;
    const moved = arrayMove(items, oldIdx, newIdx);
    setLocalOrder(moved);
    try {
      await reorderEmployees(
        moved.map((emp, idx) => ({ id: emp.id, sort_order: idx })),
      );
      await mutate();
      setLocalOrder(null);
    } catch (err) {
      setErrMsg(err instanceof Error ? err.message : "정렬 저장 실패");
      setLocalOrder(null);
    }
  }

  // 권한 체크 — 모든 hook 호출 후 (rules-of-hooks)
  if (user && !isAdmin) {
    return (
      <UnauthorizedRedirect
        targetPath="/"
        message="직원 관리는 관리자만 접근할 수 있습니다."
      />
    );
  }

  return (
    <main className="space-y-4 p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">직원 관리</h1>
          <p className="mt-0.5 text-xs text-zinc-500">
            엑셀 업로드 후 이메일/소속 등을 보강하면 회원가입 시 자동 매칭됩니다.
            민감 정보(연봉/실적 등)는 저장하지 않습니다.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="이름·이메일·소속 검색"
            className="rounded-md border border-zinc-300 bg-white px-2.5 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
          />
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
          >
            {uploading ? "업로드 중…" : "엑셀 업로드"}
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".xlsx,.xls"
            hidden
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void onUpload(f);
              e.target.value = "";
            }}
          />
          <button
            type="button"
            onClick={() => setAdding(true)}
            className="rounded-md bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700"
          >
            + 추가
          </button>
        </div>
      </header>

      <div className="flex gap-1 border-b border-zinc-200 dark:border-zinc-800">
        {(
          [
            ["active", "재직중"],
            ["resigned", "퇴사자"],
            ["all", "전체"],
          ] as const
        ).map(([k, label]) => (
          <button
            key={k}
            type="button"
            onClick={() => setView(k)}
            className={cn(
              "border-b-2 px-3 py-1.5 text-xs",
              view === k
                ? "border-blue-500 text-blue-600 dark:text-blue-400"
                : "border-transparent text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {importMsg && (
        <p className="rounded-md border border-emerald-500/40 bg-emerald-500/5 p-2 text-sm text-emerald-500">
          {importMsg}
        </p>
      )}
      {errMsg && (
        <p className="rounded-md border border-red-500/40 bg-red-500/5 p-2 text-sm text-red-500">
          {errMsg}
        </p>
      )}
      {error && (
        <p className="rounded-md border border-red-500/40 bg-red-500/5 p-2 text-sm text-red-500">
          {error instanceof Error ? error.message : "로드 실패"}
        </p>
      )}

      <div className="overflow-x-auto rounded-md border border-zinc-200 dark:border-zinc-800">
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <table className="w-full text-sm">
            <thead className="bg-zinc-50 text-left text-xs text-zinc-500 dark:bg-zinc-900">
              <tr>
                <th className="w-8 px-2 py-2"></th>
                <th className="px-3 py-2">이름</th>
                <th className="px-3 py-2">직급</th>
                <th className="px-3 py-2">소속</th>
                <th className="px-3 py-2">학위</th>
                <th className="px-3 py-2">자격</th>
                <th className="px-3 py-2">등급</th>
                <th className="px-3 py-2">이메일</th>
                <th className="px-3 py-2">계정</th>
                <th className="px-3 py-2">퇴사일</th>
                <th className="px-3 py-2 text-right">관리</th>
              </tr>
            </thead>
            <tbody>
              {adding && (
                <NewRow
                  onSaved={async () => {
                    setAdding(false);
                    await mutate();
                  }}
                  onCancel={() => setAdding(false)}
                  onError={setErrMsg}
                />
              )}
              {isLoading && !data && (
                <tr>
                  <td
                    colSpan={11}
                    className="px-3 py-8 text-center text-xs text-zinc-500"
                  >
                    불러오는 중…
                  </td>
                </tr>
              )}
              <SortableContext
                items={itemIds}
                strategy={verticalListSortingStrategy}
              >
                {displayItems.map((emp) =>
                  editId === emp.id ? (
                    <EditRow
                      key={emp.id}
                      emp={emp}
                      onSaved={async () => {
                        setEditId(null);
                        await mutate();
                      }}
                      onCancel={() => setEditId(null)}
                      onError={setErrMsg}
                    />
                  ) : (
                    <SortableRow
                      key={emp.id}
                      emp={emp}
                      dndEnabled={dndEnabled}
                      onEdit={() => setEditId(emp.id)}
                      onDelete={() => void onDelete(emp.id)}
                      onResign={() => void onResign(emp.id)}
                      onRestore={() => void onRestore(emp.id)}
                    />
                  ),
                )}
              </SortableContext>
              {data && data.items.length === 0 && (
                <tr>
                  <td
                    colSpan={11}
                    className="px-3 py-8 text-center text-xs text-zinc-500"
                  >
                    {view === "resigned"
                      ? "퇴사자 없음"
                      : "직원이 없습니다. 우상단 \"엑셀 업로드\"로 일괄 등록하세요."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </DndContext>
      </div>
      {dndEnabled && data && data.items.length > 1 && (
        <p className="text-[11px] text-zinc-500">
          ⋮⋮ 핸들을 드래그해 순서를 변경할 수 있습니다.
        </p>
      )}

      {data && (
        <p className="text-xs text-zinc-500">총 {data.count}명</p>
      )}
    </main>
  );
}

