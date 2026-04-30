"use client";

import { useMemo, useRef, useState } from "react";
import useSWR from "swr";

import { useAuth } from "@/components/AuthGuard";
import SealRequestEditModal from "@/components/project/SealRequestEditModal";
import Modal from "@/components/ui/Modal";
import LoadingState from "@/components/ui/LoadingState";
import { authFetch } from "@/lib/auth";
import { useClients } from "@/lib/hooks";
import {
  addSealAttachments,
  approveSealAdmin,
  approveSealLead,
  deleteSealRequest,
  getSealAttachmentUrl,
  listSealRequests,
  rejectSealRequest,
  type SealRequestItem,
} from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const STATUS_TABS = ["전체", "1차검토 중", "2차검토 중", "승인", "반려"] as const;
type StatusTab = (typeof STATUS_TABS)[number];

const STATUS_COLOR: Record<string, string> = {
  "1차검토 중": "bg-yellow-500/15 text-yellow-700 dark:text-yellow-400",
  "2차검토 중": "bg-blue-500/15 text-blue-700 dark:text-blue-400",
  승인: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
  반려: "bg-red-500/15 text-red-700 dark:text-red-400",
};

export default function SealRequestsPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const isAdminOrLead = isAdmin || user?.role === "team_lead";
  const myName = user?.name || user?.username || "";

  const [tab, setTab] = useState<StatusTab>("전체");
  const [selected, setSelected] = useState<SealRequestItem | null>(null);

  // docs/request.md: 일반직원은 날인요청 페이지 접근 불가
  if (user && !isAdminOrLead) {
    return (
      <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-6 text-center text-sm text-amber-600 dark:text-amber-400">
        날인요청 페이지는 팀장/관리자만 접근할 수 있습니다.
        <br />
        본인 요청 진행상황은 프로젝트 상세에서 확인하세요.
      </div>
    );
  }

  const { data, error, isLoading, mutate } = useSWR(
    user && isAdminOrLead ? ["seal-requests"] : null,
    () => listSealRequests(),
  );

  const all = useMemo(() => data?.items ?? [], [data]);
  const counts = useMemo(() => {
    const c: Record<string, number> = { 전체: all.length };
    for (const s of ["1차검토 중", "2차검토 중", "승인", "반려"]) {
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
            기술사 날인이 필요한 산출물을 검토합니다. 1차검토(팀장) → 2차검토(관리자) 흐름.
            새 요청은 프로젝트 상세에서만 등록 가능합니다.
          </p>
        </div>
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
                      {formatDate(s.requested_at)}
                      {s.due_date && (
                        <span className="ml-1 text-amber-600 dark:text-amber-400">
                          · 제출예정 {formatDate(s.due_date)}
                        </span>
                      )}
                      <span className="ml-1">· 📎 {s.attachments.length}건</span>
                    </p>
                  </div>
                  <span
                    className={cn(
                      "shrink-0 rounded-md px-2 py-0.5 text-[11px] font-medium",
                      STATUS_COLOR[s.status] ?? STATUS_COLOR["1차검토 중"],
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


function resolveClientName(
  id: string,
  clients: { id: string; name: string }[] | undefined,
): string {
  if (!id || !clients) return id;
  return clients.find((c) => c.id === id)?.name ?? id;
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
  const { data: clientData } = useClients(true);
  const clients = clientData?.items ?? [];
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const reuploadInput = useRef<HTMLInputElement>(null);

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

  const onReupload = async (list: FileList | null): Promise<void> => {
    if (!list || list.length === 0) return;
    if (
      !confirm(
        `파일 ${list.length}개를 추가하고 다시 '1차검토 중' 상태로 변경합니다. 진행할까요?`,
      )
    ) {
      if (reuploadInput.current) reuploadInput.current.value = "";
      return;
    }
    await action(() => addSealAttachments(item.id, Array.from(list)));
    if (reuploadInput.current) reuploadInput.current.value = "";
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
                STATUS_COLOR[item.status] ?? STATUS_COLOR["1차검토 중"],
              )}
            >
              {item.status}
            </span>
          </Info>
          <Info label="요청자" value={`${item.requester} · ${formatDate(item.requested_at)}`} />
          <Info
            label="제출 예정일"
            value={item.due_date ? formatDate(item.due_date) : "—"}
          />
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

        {/* docs/request.md 추가 정보 — 채워진 것만 노출 */}
        {(item.real_source_id ||
          item.purpose ||
          item.revision !== null ||
          item.with_safety_cert ||
          item.summary ||
          item.doc_no ||
          item.doc_kind) && (
          <div className="grid grid-cols-2 gap-3 rounded-md border border-zinc-200 p-2 dark:border-zinc-800">
            {item.real_source_id && (
              <Info label="실제출처" value={resolveClientName(item.real_source_id, clients)} />
            )}
            {item.purpose && <Info label="용도" value={item.purpose} />}
            {item.revision !== null && (
              <Info label="Revision" value={`rev${item.revision}`} />
            )}
            {item.with_safety_cert && (
              <Info label="안전확인서" value="포함" />
            )}
            {item.doc_no && <Info label="문서번호" value={item.doc_no} />}
            {item.doc_kind && <Info label="문서종류" value={item.doc_kind} />}
            {item.summary && (
              <div className="col-span-2">
                <p className="text-xs text-zinc-500">내용요약</p>
                <p className="mt-0.5 whitespace-pre-wrap text-sm">{item.summary}</p>
              </div>
            )}
          </div>
        )}

        {item.reject_reason && (
          <div>
            <p className="mb-1 text-xs text-red-500">반려 사유</p>
            <p className="whitespace-pre-wrap rounded-md border border-red-300 bg-red-50 p-2 text-xs text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
              {item.reject_reason}
            </p>
          </div>
        )}

        {item.folder_url && (
          <p className="text-xs">
            <a
              href={item.folder_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 hover:underline dark:text-blue-400"
            >
              📂 Works Drive 폴더 열기
            </a>
          </p>
        )}

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
                <li key={i} className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => void openAttachmentInline(item.id, i)}
                    className="flex flex-1 items-center gap-2 rounded border border-zinc-200 px-2 py-1 text-left text-xs text-blue-600 hover:bg-zinc-50 dark:border-zinc-800 dark:text-blue-400 dark:hover:bg-zinc-800"
                    title="새 탭에서 미리보기 (PDF/이미지는 inline 표시)"
                  >
                    📎 {f.name}
                  </button>
                  <button
                    type="button"
                    onClick={async () => {
                      try {
                        const r = await getSealAttachmentUrl(item.id, i);
                        const a = document.createElement("a");
                        a.href = r.url;
                        a.download = r.name;
                        a.click();
                      } catch (e) {
                        alert(
                          e instanceof Error ? e.message : "다운로드 실패",
                        );
                      }
                    }}
                    className="rounded border border-zinc-200 px-2 py-1 text-[10px] text-zinc-500 hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-800"
                    title="원본 다운로드"
                  >
                    ↓
                  </button>
                </li>
              ))}
            </ul>
          )}
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

        {item.status === "반려" && (isOwner || isAdminOrLead) && (
          <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-2 text-xs">
            <p className="mb-1 text-amber-700 dark:text-amber-400">
              반려된 요청입니다. 입력 정보를 수정하거나 파일을 보완해 재요청하면 다시 &lsquo;1차검토 중&rsquo; 상태로 진행됩니다.
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => setEditOpen(true)}
                disabled={busy}
                className="rounded-md bg-amber-500 px-3 py-1.5 text-xs text-white hover:bg-amber-600 disabled:opacity-50"
              >
                ✏️ 입력 내용 수정 / 재요청
              </button>
              <input
                ref={reuploadInput}
                type="file"
                multiple
                onChange={(e) => void onReupload(e.target.files)}
                disabled={busy}
                className="block flex-1 text-xs file:mr-2 file:rounded-md file:border-0 file:bg-amber-500 file:px-3 file:py-1.5 file:text-xs file:text-white hover:file:bg-amber-600"
              />
            </div>
          </div>
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
            {isAdminOrLead && item.status === "1차검토 중" && (
              <button
                type="button"
                onClick={() => void onApproveLead()}
                disabled={busy}
                className="rounded-md bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-700 disabled:opacity-50"
              >
                팀장 승인 (1차)
              </button>
            )}
            {isAdmin && item.status === "2차검토 중" && (
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
              (item.status === "1차검토 중" || item.status === "2차검토 중") && (
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
      {editOpen && (
        <SealRequestEditModal
          item={item}
          onClose={() => setEditOpen(false)}
          onSaved={() => {
            setEditOpen(false);
            onChanged();
          }}
        />
      )}
    </Modal>
  );
}

/** 첨부파일을 backend stream proxy(inline header)로 받아 새 탭에서 미리보기. */
async function openAttachmentInline(id: string, idx: number): Promise<void> {
  try {
    const res = await authFetch(`/api/seal-requests/${id}/preview/${idx}`);
    if (!res.ok) {
      const detail = await res
        .json()
        .then((d) => (d as { detail?: string }).detail)
        .catch(() => undefined);
      throw new Error(detail ?? `${res.status} ${res.statusText}`);
    }
    const blob = await res.blob();
    const blobUrl = URL.createObjectURL(blob);
    window.open(blobUrl, "_blank", "noopener,noreferrer");
    // 1분 후 메모리 회수 (브라우저가 다 로드한 후)
    setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000);
  } catch (e) {
    alert(e instanceof Error ? e.message : "미리보기 실패");
  }
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
