"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";

import { useAuth } from "@/components/AuthGuard";
import LoadingState from "@/components/ui/LoadingState";
import {
  createNotice,
  deleteNotice,
  listNotices,
  updateNotice,
  type Notice,
  type NoticeKind,
} from "@/lib/api";

const KINDS: NoticeKind[] = ["공지", "교육", "휴일"];

interface FormState {
  id: number | null;
  kind: NoticeKind;
  title: string;
  body: string;
  start_date: string;
  end_date: string;
}

const INITIAL_FORM: FormState = {
  id: null,
  kind: "공지",
  title: "",
  body: "",
  start_date: new Date().toISOString().slice(0, 10),
  end_date: "",
};

function formatRange(n: Notice): string {
  return n.end_date ? `${n.start_date} ~ ${n.end_date}` : `${n.start_date} ~ (무기한)`;
}

export default function AdminNoticesPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [form, setForm] = useState<FormState>(INITIAL_FORM);
  const [filterKind, setFilterKind] = useState<NoticeKind | "전체">("전체");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data, isLoading, mutate } = useSWR(
    isAdmin ? ["notices", filterKind] : null,
    () =>
      listNotices(filterKind === "전체" ? undefined : { kind: filterKind }),
  );

  const items = useMemo<Notice[]>(() => data?.items ?? [], [data]);

  if (user && !isAdmin) {
    return (
      <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-6 text-center text-sm text-amber-600 dark:text-amber-400">
        공지/교육 관리는 관리자만 접근할 수 있습니다.
      </div>
    );
  }

  const startEdit = (n: Notice): void => {
    setForm({
      id: n.id,
      kind: n.kind,
      title: n.title,
      body: n.body,
      start_date: n.start_date,
      end_date: n.end_date ?? "",
    });
    setError(null);
  };

  const resetForm = (): void => {
    setForm(INITIAL_FORM);
    setError(null);
  };

  const handleSubmit = async (e: React.FormEvent): Promise<void> => {
    e.preventDefault();
    if (!form.title.trim()) {
      setError("제목은 필수입니다");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const payload = {
        kind: form.kind,
        title: form.title.trim(),
        body: form.body.trim(),
        start_date: form.start_date,
        end_date: form.end_date || null,
      };
      if (form.id == null) {
        await createNotice(payload);
      } else {
        await updateNotice(form.id, payload);
      }
      await mutate();
      resetForm();
    } catch (err) {
      setError(err instanceof Error ? err.message : "저장 실패");
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async (id: number): Promise<void> => {
    if (!confirm("정말 삭제하시겠습니까?")) return;
    try {
      await deleteNotice(id);
      await mutate();
      if (form.id === id) resetForm();
    } catch (err) {
      alert(err instanceof Error ? err.message : "삭제 실패");
    }
  };

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">공지 / 교육 관리</h1>
        <p className="mt-1 text-sm text-zinc-500">
          주간 업무일지 1페이지의 &quot;주요 공지사항&quot; / &quot;교육 일정&quot;에 표시됩니다.
          게시기간이 보고서 주차와 겹치는 항목만 PDF에 노출.
        </p>
      </header>

      {/* 등록/수정 폼 */}
      <form
        onSubmit={handleSubmit}
        className="grid gap-3 rounded-md border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-800 dark:bg-zinc-900 md:grid-cols-2"
      >
        <div>
          <label className="block text-xs text-zinc-500">분류</label>
          <select
            value={form.kind}
            onChange={(e) =>
              setForm({ ...form, kind: e.target.value as NoticeKind })
            }
            className="mt-1 w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-950"
          >
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-zinc-500">제목</label>
          <input
            type="text"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            placeholder="예: 구조설계 업무용 폴더 체계 변경"
            className="mt-1 w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-950"
          />
        </div>
        <div>
          <label className="block text-xs text-zinc-500">게시 시작일</label>
          <input
            type="date"
            value={form.start_date}
            onChange={(e) => setForm({ ...form, start_date: e.target.value })}
            className="mt-1 w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-950"
          />
        </div>
        <div>
          <label className="block text-xs text-zinc-500">
            게시 종료일 <span className="text-zinc-400">(빈 값 = 무기한)</span>
          </label>
          <input
            type="date"
            value={form.end_date}
            onChange={(e) => setForm({ ...form, end_date: e.target.value })}
            className="mt-1 w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-950"
          />
        </div>
        <div className="md:col-span-2">
          <label className="block text-xs text-zinc-500">본문 (선택)</label>
          <textarea
            value={form.body}
            onChange={(e) => setForm({ ...form, body: e.target.value })}
            rows={2}
            className="mt-1 w-full rounded border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-950"
          />
        </div>
        {error && (
          <p className="md:col-span-2 rounded-md border border-red-500/40 bg-red-500/5 p-2 text-xs text-red-500">
            {error}
          </p>
        )}
        <div className="flex gap-2 md:col-span-2">
          <button
            type="submit"
            disabled={busy}
            className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {busy ? "저장 중..." : form.id == null ? "등록" : "수정 저장"}
          </button>
          {form.id != null && (
            <button
              type="button"
              onClick={resetForm}
              className="rounded border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
            >
              취소 (새로 등록)
            </button>
          )}
        </div>
      </form>

      {/* 필터 + 목록 */}
      <div className="flex items-center gap-2">
        <span className="text-sm text-zinc-500">필터:</span>
        {(["전체", "공지", "교육", "휴일"] as const).map((k) => (
          <button
            key={k}
            onClick={() => setFilterKind(k)}
            className={`rounded px-2 py-0.5 text-xs ${
              filterKind === k
                ? "bg-emerald-600 text-white"
                : "border border-zinc-300 dark:border-zinc-700"
            }`}
          >
            {k}
          </button>
        ))}
      </div>

      {isLoading && <LoadingState />}
      {!isLoading && items.length === 0 && (
        <div className="rounded border border-zinc-200 p-6 text-center text-sm text-zinc-500 dark:border-zinc-800">
          등록된 항목이 없습니다.
        </div>
      )}

      <ul className="space-y-2">
        {items.map((n) => (
          <li
            key={n.id}
            className="flex items-start justify-between gap-3 rounded border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-950"
          >
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span
                  className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${
                    n.kind === "교육"
                      ? "bg-blue-500/15 text-blue-700 dark:text-blue-400"
                      : n.kind === "휴일"
                        ? "bg-red-500/15 text-red-700 dark:text-red-400"
                        : "bg-amber-500/15 text-amber-700 dark:text-amber-400"
                  }`}
                >
                  {n.kind}
                </span>
                <span className="font-medium">{n.title}</span>
              </div>
              {n.body && (
                <p className="mt-1 whitespace-pre-wrap text-sm text-zinc-600 dark:text-zinc-400">
                  {n.body}
                </p>
              )}
              <p className="mt-1 text-xs text-zinc-500">{formatRange(n)}</p>
            </div>
            <div className="flex shrink-0 gap-1">
              <button
                onClick={() => startEdit(n)}
                className="rounded border border-zinc-300 px-2 py-1 text-xs hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
              >
                수정
              </button>
              <button
                onClick={() => handleDelete(n.id)}
                className="rounded border border-red-300 px-2 py-1 text-xs text-red-600 hover:bg-red-50 dark:border-red-700/40 dark:hover:bg-red-950/40"
              >
                삭제
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
