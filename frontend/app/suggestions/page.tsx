"use client";

import { useState } from "react";
import useSWR from "swr";

import { useAuth } from "@/components/AuthGuard";
import Modal from "@/components/ui/Modal";
import LoadingState from "@/components/ui/LoadingState";
import {
  createSuggestion,
  deleteSuggestion,
  listSuggestions,
  type SuggestionItem,
  updateSuggestion,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const STATUS_OPTIONS = ["접수", "검토중", "완료", "반려"] as const;

const STATUS_COLOR: Record<string, string> = {
  접수: "bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  검토중: "bg-yellow-500/20 text-yellow-700 dark:text-yellow-400",
  완료: "bg-emerald-500/20 text-emerald-700 dark:text-emerald-400",
  반려: "bg-red-500/20 text-red-700 dark:text-red-400",
};

export default function SuggestionsPage() {
  const { user } = useAuth();
  const isAdminOrLead =
    user?.role === "admin" || user?.role === "team_lead";
  const myName = user?.name || user?.username || "";

  const { data, error, isLoading, mutate } = useSWR(
    user ? ["suggestions"] : null,
    () => listSuggestions(),
  );

  const [createOpen, setCreateOpen] = useState(false);
  const [selected, setSelected] = useState<SuggestionItem | null>(null);

  const items = data?.items ?? [];

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">건의사항</h1>
          <p className="mt-1 text-sm text-zinc-500">
            업무·시스템 개선 의견을 자유롭게 등록하세요. 관리자/팀장이 진행상황과
            조치내용을 업데이트합니다.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setCreateOpen(true)}
          className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
        >
          + 새 건의
        </button>
      </header>

      {error && (
        <div className="rounded-md border border-red-500/40 bg-red-500/5 p-3 text-sm text-red-400">
          {error instanceof Error ? error.message : "건의사항 로드 실패"}
        </div>
      )}

      {isLoading && !data ? (
        <LoadingState message="불러오는 중" height="h-32" />
      ) : items.length === 0 ? (
        <p className="rounded-md border border-zinc-200 bg-white p-8 text-center text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900">
          등록된 건의사항이 없습니다.
        </p>
      ) : (
        <ul className="space-y-2">
          {items.map((s) => (
            <li key={s.id}>
              <button
                type="button"
                onClick={() => setSelected(s)}
                className="block w-full rounded-lg border border-zinc-200 bg-white p-3 text-left hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:bg-zinc-800/50"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium" title={s.title}>
                      {s.title || "(제목 없음)"}
                    </p>
                    <p className="mt-0.5 truncate text-xs text-zinc-500">
                      {s.author || "—"} · {formatDateTime(s.created_time)}
                    </p>
                  </div>
                  <span
                    className={cn(
                      "shrink-0 rounded-md px-2 py-0.5 text-[11px] font-medium",
                      STATUS_COLOR[s.status] ?? STATUS_COLOR["접수"],
                    )}
                  >
                    {s.status}
                  </span>
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}

      {createOpen && (
        <CreateModal
          onClose={() => setCreateOpen(false)}
          onCreated={() => {
            setCreateOpen(false);
            void mutate();
          }}
        />
      )}

      {selected && (
        <DetailModal
          item={selected}
          isAdminOrLead={isAdminOrLead}
          isOwner={selected.author === myName}
          onClose={() => setSelected(null)}
          onSaved={() => {
            setSelected(null);
            void mutate();
          }}
          onDeleted={() => {
            setSelected(null);
            void mutate();
          }}
        />
      )}
    </div>
  );
}

function CreateModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async (): Promise<void> => {
    if (!title.trim()) {
      setErr("제목을 입력하세요");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await createSuggestion({ title: title.trim(), content });
      onCreated();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "등록 실패");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open onClose={onClose} title="새 건의사항" size="md">
      <div className="space-y-3">
        <Field label="제목" required>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className={inputCls}
            autoFocus
          />
        </Field>
        <Field label="내용">
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={6}
            className={`${inputCls} resize-y`}
            placeholder="개선 제안이나 업무 관련 의견을 자유롭게 작성"
          />
        </Field>
        {err && (
          <p className="rounded-md border border-red-500/40 bg-red-500/5 p-2 text-xs text-red-400">
            {err}
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
            {busy ? "등록 중..." : "등록"}
          </button>
        </footer>
      </div>
    </Modal>
  );
}

function DetailModal({
  item,
  isAdminOrLead,
  isOwner,
  onClose,
  onSaved,
  onDeleted,
}: {
  item: SuggestionItem;
  isAdminOrLead: boolean;
  isOwner: boolean;
  onClose: () => void;
  onSaved: () => void;
  onDeleted: () => void;
}) {
  const [title, setTitle] = useState(item.title);
  const [content, setContent] = useState(item.content);
  const [status, setStatus] = useState(item.status);
  const [resolution, setResolution] = useState(item.resolution);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const canEditBody = isOwner || isAdminOrLead;

  const save = async (): Promise<void> => {
    setBusy(true);
    setErr(null);
    try {
      await updateSuggestion(item.id, {
        title: title === item.title ? undefined : title,
        content: content === item.content ? undefined : content,
        status:
          isAdminOrLead && status !== item.status ? status : undefined,
        resolution:
          isAdminOrLead && resolution !== item.resolution
            ? resolution
            : undefined,
      });
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "저장 실패");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (): Promise<void> => {
    if (!confirm(`"${item.title}" 건의를 삭제하시겠습니까?`)) return;
    setBusy(true);
    try {
      await deleteSuggestion(item.id);
      onDeleted();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "삭제 실패");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open onClose={onClose} title={`건의 — ${item.author || "—"}`} size="lg">
      <div className="space-y-3">
        <Field label="제목">
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            disabled={!canEditBody}
            className={cn(inputCls, !canEditBody && "opacity-70")}
          />
        </Field>
        <Field label="내용">
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            disabled={!canEditBody}
            rows={6}
            className={cn(inputCls, "resize-y", !canEditBody && "opacity-70")}
          />
        </Field>

        <div className="border-t border-zinc-200 pt-3 dark:border-zinc-800">
          <p className="mb-2 text-xs font-semibold text-zinc-700 dark:text-zinc-300">
            관리자 / 팀장 전용
          </p>
          <Field label="진행상황">
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              disabled={!isAdminOrLead}
              className={cn(inputCls, !isAdminOrLead && "opacity-70")}
            >
              {STATUS_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </Field>
          <Field label="조치내용">
            <textarea
              value={resolution}
              onChange={(e) => setResolution(e.target.value)}
              disabled={!isAdminOrLead}
              rows={4}
              className={cn(
                inputCls,
                "resize-y",
                !isAdminOrLead && "opacity-70",
              )}
              placeholder={
                isAdminOrLead ? "어떻게 처리했는지 기록" : "(관리자/팀장만 작성)"
              }
            />
          </Field>
        </div>

        {err && (
          <p className="rounded-md border border-red-500/40 bg-red-500/5 p-2 text-xs text-red-400">
            {err}
          </p>
        )}

        <footer className="flex items-center justify-between gap-2 pt-2">
          {(isOwner || isAdminOrLead) && (
            <button
              type="button"
              onClick={remove}
              disabled={busy}
              className="text-xs text-red-500 hover:underline disabled:opacity-50"
            >
              삭제
            </button>
          )}
          <div className="ml-auto flex gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={busy}
              className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
            >
              {canEditBody || isAdminOrLead ? "취소" : "닫기"}
            </button>
            {(canEditBody || isAdminOrLead) && (
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
