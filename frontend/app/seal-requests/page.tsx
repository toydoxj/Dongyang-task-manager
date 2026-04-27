"use client";

import { useMemo, useRef, useState } from "react";
import useSWR from "swr";

import { useAuth } from "@/components/AuthGuard";
import Modal from "@/components/ui/Modal";
import LoadingState from "@/components/ui/LoadingState";
import {
  approveSealAdmin,
  approveSealLead,
  createSealRequest,
  deleteSealRequest,
  listSealRequests,
  rejectSealRequest,
  type SealRequestItem,
} from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/format";
import { useProjects } from "@/lib/hooks";
import { cn } from "@/lib/utils";

const SEAL_TYPES = ["구조계산서", "도면", "검토서", "기타"] as const;
const STATUS_TABS = ["전체", "요청", "팀장승인", "완료", "반려"] as const;
type StatusTab = (typeof STATUS_TABS)[number];

const STATUS_COLOR: Record<string, string> = {
  요청: "bg-yellow-500/15 text-yellow-700 dark:text-yellow-400",
  팀장승인: "bg-blue-500/15 text-blue-700 dark:text-blue-400",
  완료: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
  반려: "bg-red-500/15 text-red-700 dark:text-red-400",
};

export default function SealRequestsPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const isAdminOrLead = isAdmin || user?.role === "team_lead";
  const myName = user?.name || user?.username || "";

  const [tab, setTab] = useState<StatusTab>("전체");
  const [createOpen, setCreateOpen] = useState(false);
  const [selected, setSelected] = useState<SealRequestItem | null>(null);

  const { data, error, isLoading, mutate } = useSWR(
    user ? ["seal-requests"] : null,
    () => listSealRequests(),
  );

  const all = useMemo(() => data?.items ?? [], [data]);
  const counts = useMemo(() => {
    const c: Record<string, number> = { 전체: all.length };
    for (const s of ["요청", "팀장승인", "완료", "반려"]) {
      c[s] = all.filter((x) => x.status === s).length;
    }
    return c;
  }, [all]);

  const filtered = tab === "전체" ? all : all.filter((x) => x.status === tab);

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">날인요청</h1>
          <p className="mt-1 text-sm text-zinc-500">
            기술사 날인이 필요한 산출물을 요청합니다. 팀장 1차 승인 → 관리자 최종
            승인 흐름.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setCreateOpen(true)}
          className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
        >
          + 새 요청
        </button>
      </header>

      <div className="flex gap-1 border-b border-zinc-200 dark:border-zinc-800">
        {STATUS_TABS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setTab(s)}
            className={cn(
              "border-b-2 px-3 py-1.5 text-xs",
              tab === s
                ? "border-blue-500 text-blue-600 dark:text-blue-400"
                : "border-transparent text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300",
            )}
          >
            {s} <span className="ml-1 text-zinc-400">({counts[s] ?? 0})</span>
          </button>
        ))}
      </div>

      {error && (
        <p className="rounded-md border border-red-500/40 bg-red-500/5 p-3 text-sm text-red-400">
          {error instanceof Error ? error.message : "로드 실패"}
        </p>
      )}

      {isLoading && !data ? (
        <LoadingState message="불러오는 중" height="h-32" />
      ) : filtered.length === 0 ? (
        <p className="rounded-md border border-zinc-200 bg-white p-8 text-center text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900">
          {tab === "전체" ? "등록된 요청이 없습니다." : `${tab} 상태의 요청이 없습니다.`}
        </p>
      ) : (
        <ul className="space-y-2">
          {filtered.map((s) => (
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
                      {s.seal_type} · {s.requester} ·{" "}
                      {formatDate(s.requested_at)} ·{" "}
                      📎 {s.attachments.length}건
                    </p>
                  </div>
                  <span
                    className={cn(
                      "shrink-0 rounded-md px-2 py-0.5 text-[11px] font-medium",
                      STATUS_COLOR[s.status] ?? STATUS_COLOR["요청"],
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
          isAdmin={isAdmin}
          isAdminOrLead={isAdminOrLead}
          isOwner={selected.requester === myName}
          onClose={() => setSelected(null)}
          onChanged={() => {
            void mutate();
            setSelected(null);
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
  const { user } = useAuth();
  const { data: projectData } = useProjects(
    user?.name ? { mine: true } : undefined,
  );
  const myProjects = projectData?.items ?? [];

  const [projectId, setProjectId] = useState("");
  const [sealType, setSealType] = useState<string>("구조계산서");
  const [title, setTitle] = useState("");
  const [note, setNote] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const submit = async (): Promise<void> => {
    if (!projectId) {
      setErr("프로젝트를 선택하세요");
      return;
    }
    if (files.length === 0) {
      setErr("첨부파일을 1개 이상 추가하세요");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const fd = new FormData();
      fd.append("project_id", projectId);
      fd.append("seal_type", sealType);
      fd.append("title", title);
      fd.append("note", note);
      for (const f of files) fd.append("files", f);
      await createSealRequest(fd);
      onCreated();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "등록 실패");
    } finally {
      setBusy(false);
    }
  };

  const onPickFiles = (list: FileList | null): void => {
    if (!list) return;
    setFiles((prev) => [...prev, ...Array.from(list)]);
    if (fileInput.current) fileInput.current.value = "";
  };

  return (
    <Modal open onClose={onClose} title="새 날인요청" size="md">
      <div className="space-y-3">
        <Field label="프로젝트" required>
          <select
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            className={inputCls}
          >
            <option value="">— 선택하세요</option>
            {myProjects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.code ? `[${p.code}] ` : ""}
                {p.name}
              </option>
            ))}
          </select>
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="날인유형" required>
            <select
              value={sealType}
              onChange={(e) => setSealType(e.target.value)}
              className={inputCls}
            >
              {SEAL_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </Field>
          <Field label="제목 (선택)">
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="비워두면 자동 생성"
              className={inputCls}
            />
          </Field>
        </div>

        <Field label="비고">
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={3}
            className={`${inputCls} resize-y`}
          />
        </Field>

        <Field label="첨부파일 (다중 가능, 파일당 ≤20MB)" required>
          <input
            ref={fileInput}
            type="file"
            multiple
            onChange={(e) => onPickFiles(e.target.files)}
            className="block w-full text-xs file:mr-2 file:rounded-md file:border-0 file:bg-zinc-100 file:px-3 file:py-1.5 file:text-xs hover:file:bg-zinc-200 dark:file:bg-zinc-800 dark:file:text-zinc-100"
          />
          {files.length > 0 && (
            <ul className="mt-2 space-y-1 text-xs">
              {files.map((f, i) => (
                <li
                  key={i}
                  className="flex items-center justify-between rounded border border-zinc-200 px-2 py-1 dark:border-zinc-800"
                >
                  <span className="truncate" title={f.name}>
                    📎 {f.name} <span className="text-zinc-400">({Math.round(f.size / 1024)} KB)</span>
                  </span>
                  <button
                    type="button"
                    onClick={() => setFiles((prev) => prev.filter((_, j) => j !== i))}
                    className="text-zinc-400 hover:text-red-500"
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          )}
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
  isAdmin,
  isAdminOrLead,
  isOwner,
  onClose,
  onChanged,
}: {
  item: SealRequestItem;
  isAdmin: boolean;
  isAdminOrLead: boolean;
  isOwner: boolean;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const action = async (fn: () => Promise<unknown>): Promise<void> => {
    setBusy(true);
    setErr(null);
    try {
      await fn();
      onChanged();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "처리 실패");
    } finally {
      setBusy(false);
    }
  };

  const onApproveLead = (): Promise<void> => action(() => approveSealLead(item.id));
  const onApproveAdmin = (): Promise<void> => action(() => approveSealAdmin(item.id));
  const onReject = (): Promise<void> => {
    const reason = prompt("반려 사유를 입력하세요") ?? "";
    if (!reason.trim()) return Promise.resolve();
    return action(() => rejectSealRequest(item.id, reason.trim()));
  };
  const onDelete = (): Promise<void> => {
    if (!confirm("삭제하시겠습니까? (노션 보관 처리)")) return Promise.resolve();
    return action(() => deleteSealRequest(item.id));
  };

  return (
    <Modal open onClose={onClose} title={item.title || "(제목 없음)"} size="lg">
      <div className="space-y-3 text-sm">
        <div className="grid grid-cols-2 gap-3">
          <Info label="날인유형" value={item.seal_type} />
          <Info label="상태">
            <span
              className={cn(
                "rounded-md px-2 py-0.5 text-[11px] font-medium",
                STATUS_COLOR[item.status] ?? STATUS_COLOR["요청"],
              )}
            >
              {item.status}
            </span>
          </Info>
          <Info label="요청자" value={`${item.requester} · ${formatDate(item.requested_at)}`} />
          <Info
            label="처리"
            value={
              [
                item.lead_handler && `1차: ${item.lead_handler} (${formatDate(item.lead_handled_at)})`,
                item.admin_handler && `최종: ${item.admin_handler} (${formatDate(item.admin_handled_at)})`,
              ]
                .filter(Boolean)
                .join("\n") || "—"
            }
          />
        </div>

        {item.note && (
          <div>
            <p className="mb-1 text-xs text-zinc-500">비고</p>
            <p className="whitespace-pre-wrap rounded-md bg-zinc-50 p-2 text-xs dark:bg-zinc-800">
              {item.note}
            </p>
          </div>
        )}

        <div>
          <p className="mb-1 text-xs text-zinc-500">첨부파일 ({item.attachments.length})</p>
          {item.attachments.length === 0 ? (
            <p className="text-xs text-zinc-400">첨부 없음</p>
          ) : (
            <ul className="space-y-1">
              {item.attachments.map((f, i) => (
                <li key={i}>
                  <a
                    href={f.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-2 rounded border border-zinc-200 px-2 py-1 text-xs text-blue-600 hover:bg-zinc-50 dark:border-zinc-800 dark:text-blue-400 dark:hover:bg-zinc-800"
                  >
                    📎 {f.name}
                  </a>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-1 text-[10px] text-zinc-400">
            노션 호스팅 파일 URL은 1시간 후 만료됩니다. 새로고침 시 갱신.
          </p>
        </div>

        <p className="text-[10px] text-zinc-400">
          생성: {formatDateTime(item.created_time)} · 수정:{" "}
          {formatDateTime(item.last_edited_time)}
        </p>

        {err && (
          <p className="rounded-md border border-red-500/40 bg-red-500/5 p-2 text-xs text-red-400">
            {err}
          </p>
        )}

        <footer className="flex items-center justify-between gap-2 pt-2">
          <div className="flex gap-2">
            {(isOwner || isAdmin) && (
              <button
                type="button"
                onClick={() => void onDelete()}
                disabled={busy}
                className="text-xs text-red-500 hover:underline disabled:opacity-50"
              >
                삭제
              </button>
            )}
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            {isAdminOrLead && item.status === "요청" && (
              <button
                type="button"
                onClick={() => void onApproveLead()}
                disabled={busy}
                className="rounded-md bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-700 disabled:opacity-50"
              >
                팀장 승인 (1차)
              </button>
            )}
            {isAdmin && item.status === "팀장승인" && (
              <button
                type="button"
                onClick={() => void onApproveAdmin()}
                disabled={busy}
                className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs text-white hover:bg-emerald-700 disabled:opacity-50"
              >
                관리자 최종 승인
              </button>
            )}
            {isAdminOrLead &&
              (item.status === "요청" || item.status === "팀장승인") && (
                <button
                  type="button"
                  onClick={() => void onReject()}
                  disabled={busy}
                  className="rounded-md border border-red-300 px-3 py-1.5 text-xs text-red-500 hover:bg-red-50 dark:border-red-900 dark:hover:bg-red-950"
                >
                  반려
                </button>
              )}
            <button
              type="button"
              onClick={onClose}
              disabled={busy}
              className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
            >
              닫기
            </button>
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

function Info({
  label,
  value,
  children,
}: {
  label: string;
  value?: string;
  children?: React.ReactNode;
}) {
  return (
    <div>
      <p className="text-xs text-zinc-500">{label}</p>
      <div className="mt-0.5 whitespace-pre-line text-sm">{children ?? value ?? "—"}</div>
    </div>
  );
}
