"use client";

import { useEffect, useRef, useState } from "react";
import useSWR from "swr";

import { useAuth } from "@/components/AuthGuard";
import {
  createEmployee,
  deleteEmployee,
  listEmployees,
  updateEmployee,
  uploadEmployees,
} from "@/lib/api";
import type {
  Employee,
  EmployeeCreate,
  EmployeeImportResult,
} from "@/lib/domain";
import { cn } from "@/lib/utils";

export default function EmployeesAdminPage() {
  const { user } = useAuth();
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const { data, isLoading, mutate, error } = useSWR(
    user?.role === "admin" ? ["employees", debouncedQ] : null,
    () => listEmployees(debouncedQ || undefined),
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

  if (user && user.role !== "admin") {
    return (
      <main className="p-6">
        <p className="text-sm text-red-500">관리자 권한이 필요합니다.</p>
      </main>
    );
  }

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
    if (!confirm("이 직원을 삭제하시겠습니까?")) return;
    try {
      await deleteEmployee(id);
      await mutate();
    } catch (e) {
      setErrMsg(e instanceof Error ? e.message : "삭제 실패");
    }
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
        <table className="w-full text-sm">
          <thead className="bg-zinc-50 text-left text-xs text-zinc-500 dark:bg-zinc-900">
            <tr>
              <th className="px-3 py-2">이름</th>
              <th className="px-3 py-2">직급</th>
              <th className="px-3 py-2">소속</th>
              <th className="px-3 py-2">학위</th>
              <th className="px-3 py-2">자격</th>
              <th className="px-3 py-2">등급</th>
              <th className="px-3 py-2">이메일</th>
              <th className="px-3 py-2">계정</th>
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
                <td colSpan={9} className="px-3 py-8 text-center text-xs text-zinc-500">
                  불러오는 중…
                </td>
              </tr>
            )}
            {data?.items.map((emp) =>
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
                <ViewRow
                  key={emp.id}
                  emp={emp}
                  onEdit={() => setEditId(emp.id)}
                  onDelete={() => void onDelete(emp.id)}
                />
              ),
            )}
            {data && data.items.length === 0 && (
              <tr>
                <td colSpan={9} className="px-3 py-8 text-center text-xs text-zinc-500">
                  직원이 없습니다. 우상단 &quot;엑셀 업로드&quot;로 일괄 등록하세요.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {data && (
        <p className="text-xs text-zinc-500">총 {data.count}명</p>
      )}
    </main>
  );
}

const cellCls = "px-3 py-2 align-top";
const inputCls =
  "w-full rounded border border-zinc-300 bg-white px-2 py-1 text-xs dark:border-zinc-700 dark:bg-zinc-950";

function ViewRow({
  emp,
  onEdit,
  onDelete,
}: {
  emp: Employee;
  onEdit: () => void;
  onDelete: () => void;
}) {
  return (
    <tr className="border-t border-zinc-200 hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900">
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
      <td className={cn(cellCls, "text-right")}>
        <button
          type="button"
          onClick={onEdit}
          className="rounded border border-zinc-300 px-2 py-0.5 text-[11px] hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
        >
          편집
        </button>
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

function EditRow({
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

function NewRow({
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
