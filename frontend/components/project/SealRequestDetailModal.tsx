"use client";

/**
 * 프로젝트 상세에서 날인 항목을 클릭했을 때 띄우는 read-only 상세 모달.
 * 하단에 "재날인요청" 버튼 — 클릭 시 부모가 SealRequestCreateModal을
 * redoFrom prefill로 띄우게 onRedo 콜백을 호출.
 *
 * 일반 직원(member)도 본인 프로젝트의 날인 진행 상황을 확인 가능.
 */

import Modal from "@/components/ui/Modal";
import { useClients } from "@/lib/hooks";
import type { SealRequestItem } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const STATUS_COLOR: Record<string, string> = {
  "1차검토 중": "bg-yellow-500/15 text-yellow-700 dark:text-yellow-400",
  "2차검토 중": "bg-blue-500/15 text-blue-700 dark:text-blue-400",
  승인: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
  반려: "bg-red-500/15 text-red-700 dark:text-red-400",
};

interface Props {
  item: SealRequestItem;
  onClose: () => void;
  onRedo: (item: SealRequestItem) => void;
}

export default function SealRequestDetailModal({
  item,
  onClose,
  onRedo,
}: Props) {
  const { data: clientData } = useClients(true);
  const clients = clientData?.items ?? [];
  const realSourceName = item.real_source_id
    ? (clients.find((c) => c.id === item.real_source_id)?.name ??
       item.real_source_id)
    : "";

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
          <Info
            label="요청자"
            value={`${item.requester} · ${formatDate(item.requested_at)}`}
          />
          <Info
            label="제출 예정일"
            value={item.due_date ? formatDate(item.due_date) : "—"}
          />
          <Info
            label="처리"
            value={
              [
                item.lead_handler &&
                  `1차: ${item.lead_handler} (${formatDate(item.lead_handled_at)})`,
                item.admin_handler &&
                  `최종: ${item.admin_handler} (${formatDate(item.admin_handled_at)})`,
              ]
                .filter(Boolean)
                .join("\n") || "—"
            }
          />
        </div>

        {(realSourceName ||
          item.purpose ||
          item.revision !== null ||
          item.with_safety_cert ||
          item.summary ||
          item.doc_no ||
          item.doc_kind) && (
          <div className="grid grid-cols-2 gap-3 rounded-md border border-zinc-200 p-2 dark:border-zinc-800">
            {realSourceName && (
              <Info label="실제출처" value={realSourceName} />
            )}
            {item.purpose && <Info label="용도" value={item.purpose} />}
            {item.revision !== null && (
              <Info label="Revision" value={`rev${item.revision}`} />
            )}
            {item.with_safety_cert && <Info label="안전확인서" value="포함" />}
            {item.doc_no && <Info label="문서번호" value={item.doc_no} />}
            {item.doc_kind && <Info label="문서종류" value={item.doc_kind} />}
            {item.summary && (
              <div className="col-span-2">
                <p className="text-xs text-zinc-500">내용요약</p>
                <p className="mt-0.5 whitespace-pre-wrap text-sm">
                  {item.summary}
                </p>
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

        <p className="text-[10px] text-zinc-400">
          생성: {formatDateTime(item.created_time)} · 수정:{" "}
          {formatDateTime(item.last_edited_time)}
        </p>

        <footer className="flex items-center justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={() => onRedo(item)}
            className="rounded-md bg-amber-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-600"
            title="이전 내용을 그대로 가져와 새 날인요청을 등록합니다"
          >
            🔁 재날인요청
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
          >
            닫기
          </button>
        </footer>
      </div>
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
      <div className="mt-0.5 whitespace-pre-line text-sm">
        {children ?? value ?? "—"}
      </div>
    </div>
  );
}
