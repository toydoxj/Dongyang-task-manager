"use client";

/**
 * /seal-requests 페이지 — 날인요청 상세 모달.
 * 1차/최종 승인·반려·삭제·재요청 + Drive 폴더 link + Info row.
 *
 * PR-AZ — page.tsx에서 추출 (외과적 변경 / 동작 동일).
 */

import { useMemo, useState } from "react";

import { useAuth } from "@/components/AuthGuard";
import DriveExplorerModal from "@/components/project/DriveExplorerModal";
import SealRequestEditModal from "@/components/project/SealRequestEditModal";
import Modal from "@/components/ui/Modal";
import {
  approveSealAdmin,
  approveSealLead,
  deleteSealRequest,
  rejectSealRequest,
  type SealRequestItem,
} from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/format";
import { useClients, useProject } from "@/lib/hooks";
import { cn } from "@/lib/utils";

import { extractResourceKey, resolveClientName, STATUS_COLOR } from "./_utils";

export default function DetailModal({
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
  const { driveLocalRoot } = useAuth();
  const { data: clientData } = useClients(true);
  const clients = useMemo(() => clientData?.items ?? [], [clientData]);
  // 프로젝트명/발주처 표시용 — 첫 번째 project_id로 lookup
  const projectId = item.project_ids?.[0] ?? "";
  const { data: project } = useProject(projectId || null);
  const projectClientLabel = useMemo<string>(() => {
    if (item.real_source_id) {
      return clients.find((c) => c.id === item.real_source_id)?.name ?? "";
    }
    if (!project) return "";
    if (project.client_names?.length) return project.client_names.join(", ");
    return project.client_text ?? "";
  }, [item.real_source_id, project, clients]);

  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [explorerOpen, setExplorerOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  // 검토자료 폴더 fileId — folder_url에서 추출
  const folderFileId = useMemo(
    () => extractResourceKey(item.folder_url),
    [item.folder_url],
  );

  // PC 경로: {driveLocalRoot}\[코드]프로젝트명\0.검토자료\YYYYMMDD
  // YYYYMMDD는 요청일 기준 (대부분 폴더 생성일과 동일)
  const folderName =
    project?.code && project?.name
      ? `[${project.code}]${project.name}`
      : "";
  const ymd = useMemo(() => {
    const d = item.requested_at ? new Date(item.requested_at) : new Date();
    if (Number.isNaN(d.getTime())) return "";
    return (
      `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}` +
      `${String(d.getDate()).padStart(2, "0")}`
    );
  }, [item.requested_at]);
  const localPath =
    driveLocalRoot && folderName
      ? `${driveLocalRoot}\\${folderName}\\0.검토자료${ymd ? "\\" + ymd : ""}`
      : "";

  const copyLocalPath = async (): Promise<void> => {
    if (!localPath) return;
    try {
      await navigator.clipboard.writeText(localPath);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      window.prompt("아래 경로를 복사하세요 (Ctrl+C):", localPath);
    }
  };

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
        {/* 프로젝트명 + 발주처(실제출처) */}
        <div className="grid grid-cols-2 gap-3 rounded-md border border-zinc-200 p-2 dark:border-zinc-800">
          <Info
            label="프로젝트"
            value={
              project
                ? `${project.code ? `[${project.code}] ` : ""}${project.name}`
                : projectId
                  ? "불러오는 중..."
                  : "—"
            }
          />
          <Info
            label={item.real_source_id ? "발주처(실제출처)" : "발주처"}
            value={projectClientLabel || "—"}
          />
        </div>

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
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            {folderFileId && (
              <button
                type="button"
                onClick={() => setExplorerOpen(true)}
                className="inline-flex items-center gap-1 rounded-md border border-amber-700/40 bg-amber-600/10 px-2.5 py-1 font-medium text-amber-700 hover:bg-amber-600/20 dark:text-amber-300"
                title="앱 안에서 폴더 트리 탐색"
              >
                🗂️ 폴더 열기
              </button>
            )}
            <a
              href={item.folder_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 rounded-md border border-emerald-700/40 bg-emerald-600/10 px-2.5 py-1 font-medium text-emerald-700 hover:bg-emerald-600/20 dark:text-emerald-300"
              title="WORKS Drive 웹에서 폴더 열기"
            >
              🌐 WORKS Drive
            </a>
            {localPath && (
              <button
                type="button"
                onClick={() => void copyLocalPath()}
                className="inline-flex items-center gap-1 rounded-md border border-blue-700/40 bg-blue-600/10 px-2.5 py-1 font-medium text-blue-700 hover:bg-blue-600/20 dark:text-blue-300"
                title={localPath}
              >
                📁 {copied ? "복사됨!" : "PC 경로 복사"}
              </button>
            )}
          </div>
        )}

        {item.note && (
          <div>
            <p className="mb-1 text-xs text-zinc-500">비고</p>
            <p className="whitespace-pre-wrap rounded-md bg-zinc-50 p-2 text-xs dark:bg-zinc-800">
              {item.note}
            </p>
          </div>
        )}

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
              반려된 요청입니다. 입력 정보를 수정한 뒤 재요청하면 다시 &lsquo;1차검토 중&rsquo;으로 진행됩니다.
              파일은 NAVER WORKS Drive 검토자료 폴더에서 직접 보완하세요.
            </p>
            <button
              type="button"
              onClick={() => setEditOpen(true)}
              disabled={busy}
              className="rounded-md bg-amber-500 px-3 py-1.5 text-xs text-white hover:bg-amber-600 disabled:opacity-50"
            >
              ✏️ 입력 내용 수정 / 재요청
            </button>
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
            {/* 반려는 현재 단계의 검토자만 가능: 1차검토 중→팀장/관리자, 2차검토 중→관리자 */}
            {((item.status === "1차검토 중" && isAdminOrLead) ||
              (item.status === "2차검토 중" && isAdmin)) && (
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
      {explorerOpen && project && folderFileId && (
        <DriveExplorerModal
          open={explorerOpen}
          onClose={() => setExplorerOpen(false)}
          projectId={project.id}
          rootLabel={folderName || project.name || "프로젝트 폴더"}
          initialFolderId={folderFileId}
          initialFolderLabel={`0.검토자료${ymd ? "/" + ymd : ""}`}
        />
      )}
    </Modal>
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
