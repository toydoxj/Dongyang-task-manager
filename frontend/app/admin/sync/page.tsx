"use client";

/**
 * /admin/sync — 노션 미러 동기화 관리 (admin only).
 *
 * 업무시간(KST 06~20시)에는 Render cron이 멈춰 있어 노션 변경이 즉시 반영
 * 안 됨. 운영 중 즉시 sync가 필요하면 여기서 트리거.
 *
 * PR-AR.
 */

import { useState } from "react";
import useSWR from "swr";

import { useAuth } from "@/components/AuthGuard";
import UnauthorizedRedirect from "@/components/UnauthorizedRedirect";
import LoadingState from "@/components/ui/LoadingState";
import {
  adminSyncRun,
  adminSyncStatus,
  type SyncStatusItem,
} from "@/lib/api";

const KIND_LABEL: Record<string, string> = {
  projects: "프로젝트",
  tasks: "업무 TASK",
  clients: "발주처",
  master: "마스터 프로젝트",
  cashflow: "수금",
  expense: "지출",
  contract_items: "계약 분담",
  sales: "영업",
};

function formatTime(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Intl.DateTimeFormat("ko-KR", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: "Asia/Seoul",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

function relativeTime(iso: string | null): string {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const diffMs = Date.now() - t;
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return "방금 전";
  if (diffMin < 60) return `${diffMin}분 전`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}시간 전`;
  const diffDay = Math.floor(diffHr / 24);
  return `${diffDay}일 전`;
}

export default function AdminSyncPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const { data, error, isLoading, mutate } = useSWR(
    isAdmin ? ["admin-sync-status"] : null,
    () => adminSyncStatus(),
    { refreshInterval: 10_000 }, // 10초마다 자동 갱신
  );

  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  if (!isAdmin) {
    return (
      <UnauthorizedRedirect
        targetPath="/dashboard"
        message="관리자만 접근 가능합니다."
      />
    );
  }

  const run = async (kind?: string, full?: boolean): Promise<void> => {
    setBusy(kind ?? "_all");
    setMsg(null);
    try {
      const res = await adminSyncRun({ kind, full });
      setMsg(
        `[${kind ? KIND_LABEL[kind] ?? kind : "전체"}] ${
          res.status === "started" ? "실행 시작" : res.status
        }${full ? " (full)" : ""}`,
      );
      // 즉시 한번 갱신, 그 후 SWR refreshInterval로 추적
      setTimeout(() => {
        void mutate();
      }, 1500);
    } catch (e) {
      setMsg(`실패: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">Sync 관리</h1>
        <p className="mt-1 text-sm text-zinc-500">
          노션 미러 동기화 — 정기 cron은 업무시간(KST 06~20시)에는 멈춤. 운영 중
          즉시 sync 필요 시 본 페이지에서 트리거.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-2 rounded-md border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-900">
        <button
          type="button"
          onClick={() => run()}
          disabled={busy !== null}
          className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
        >
          {busy === "_all" ? "실행 중..." : "전체 sync (incremental)"}
        </button>
        <button
          type="button"
          onClick={() => run(undefined, true)}
          disabled={busy !== null}
          className="rounded border border-amber-600 bg-white px-3 py-1.5 text-sm font-medium text-amber-700 hover:bg-amber-50 disabled:opacity-50 dark:bg-zinc-900 dark:text-amber-400 dark:hover:bg-amber-950/30"
          title="archive된 row 정리까지 — 시간 더 걸림 (보통 새벽 03시 cron)"
        >
          전체 sync (full reconcile)
        </button>
        {msg && (
          <span className="ml-2 text-xs text-zinc-600 dark:text-zinc-400">
            {msg}
          </span>
        )}
      </div>

      {isLoading && <LoadingState />}
      {error && (
        <div className="rounded-md border border-red-500/40 bg-red-500/5 p-3 text-sm text-red-600 dark:text-red-400">
          상태 조회 실패: {error instanceof Error ? error.message : String(error)}
        </div>
      )}

      {data && (
        <div className="overflow-x-auto rounded-md border border-zinc-200 dark:border-zinc-800">
          <table className="w-full text-sm">
            <thead className="bg-zinc-100 dark:bg-zinc-900">
              <tr className="text-left">
                <th className="px-3 py-2 font-medium">종류</th>
                <th className="px-3 py-2 font-medium">마지막 incremental</th>
                <th className="px-3 py-2 font-medium">마지막 full</th>
                <th className="px-3 py-2 text-right font-medium">최근 건수</th>
                <th className="px-3 py-2 font-medium">에러</th>
                <th className="px-3 py-2 text-right font-medium">조작</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((it: SyncStatusItem) => (
                <tr
                  key={it.kind}
                  className="border-t border-zinc-200 dark:border-zinc-800"
                >
                  <td className="px-3 py-2 font-medium">
                    {KIND_LABEL[it.kind] ?? it.kind}{" "}
                    <span className="text-[10px] text-zinc-400">
                      ({it.kind})
                    </span>
                  </td>
                  <td className="px-3 py-2 text-zinc-600 dark:text-zinc-400">
                    {formatTime(it.last_incremental_synced_at)}
                    <span className="ml-1 text-[10px] text-zinc-400">
                      {relativeTime(it.last_incremental_synced_at)}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-zinc-600 dark:text-zinc-400">
                    {formatTime(it.last_full_synced_at)}
                    <span className="ml-1 text-[10px] text-zinc-400">
                      {relativeTime(it.last_full_synced_at)}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {it.last_run_count}
                  </td>
                  <td className="px-3 py-2">
                    {it.last_error ? (
                      <span
                        className="text-xs text-red-600 dark:text-red-400"
                        title={it.last_error}
                      >
                        ⚠ {it.last_error.slice(0, 40)}
                        {it.last_error.length > 40 && "..."}
                      </span>
                    ) : (
                      <span className="text-xs text-zinc-400">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      type="button"
                      onClick={() => run(it.kind)}
                      disabled={busy !== null}
                      className="rounded border border-zinc-300 px-2 py-1 text-xs hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
                    >
                      {busy === it.kind ? "..." : "sync"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-[11px] text-zinc-500">
        ※ 표는 10초마다 자동 갱신. sync는 fire-and-forget으로 진행 — 결과는 위
        시각/건수가 갱신되면 완료. 에러 발생 시 backend Logs(Render) 확인 권장.
      </p>
    </div>
  );
}
