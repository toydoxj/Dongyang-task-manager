"use client";

/**
 * /admin/sync — 노션 미러 동기화 관리 (admin only).
 *
 * 정기 full reconcile은 매일 새벽 03시(KST)에 실행된다.
 * outbox drain은 5분마다 실행된다.
 * 운영 중 즉시 sync가 필요하면 여기서 web service background task로 트리거.
 *
 * PR-AR.
 */

import { useState } from "react";
import useSWR from "swr";

import { useRoleGuard } from "@/lib/useRoleGuard";
import UnauthorizedRedirect from "@/components/UnauthorizedRedirect";
import LoadingState from "@/components/ui/LoadingState";
import {
  adminOutboxDrain,
  adminOutboxStatus,
  adminSyncRun,
  adminSyncRuns,
  adminSyncStatus,
  type OutboxStatusEntry,
  type SyncRunLogItem,
  type SyncStatusItem,
} from "@/lib/api";

const STALE_FULL_MS = 26 * 60 * 60 * 1000;

const KIND_LABEL: Record<string, string> = {
  projects: "프로젝트",
  tasks: "업무 TASK",
  clients: "발주처",
  master: "마스터 프로젝트",
  cashflow: "수금",
  expense: "지출",
  contract_items: "계약 분담",
  sales: "영업",
  seal_requests: "날인요청",
  suggestions: "건의사항",
};

const OUTBOX_LABEL: Record<string, string> = {
  pending: "대기",
  processing: "처리 중",
  retry: "재시도",
  sent: "완료",
  dead: "실패",
};
const OUTBOX_STATUSES = [
  "pending",
  "processing",
  "retry",
  "sent",
  "dead",
] as const;

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

function formatElapsed(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 60) return `${seconds.toFixed(1)}초`;
  const min = Math.floor(seconds / 60);
  const sec = Math.round(seconds % 60);
  return `${min}분 ${sec}초`;
}

function isFullStale(iso: string | null): boolean {
  if (!iso) return true;
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return true;
  return Date.now() - t > STALE_FULL_MS;
}

function statusLabel(status: string): string {
  if (status === "running") return "진행 중";
  if (status === "success") return "완료";
  if (status === "partial_failed") return "일부 실패";
  if (status === "failed") return "실패";
  return status;
}

function statusClass(status: string): string {
  if (status === "running") return "text-sky-600 dark:text-sky-400";
  if (status === "success") return "text-emerald-600 dark:text-emerald-400";
  if (status === "partial_failed") return "text-amber-600 dark:text-amber-400";
  if (status === "failed") return "text-red-600 dark:text-red-400";
  return "text-zinc-600 dark:text-zinc-400";
}

function sourceLabel(source: string): string {
  if (source === "manual") return "수동";
  if (source === "cron") return "cron";
  return source;
}

function runTarget(run: SyncRunLogItem): string {
  return run.kind ? KIND_LABEL[run.kind] ?? run.kind : "전체";
}

function outboxLabel(status: string): string {
  return OUTBOX_LABEL[status] ?? status;
}

function outboxClass(status: string): string {
  if (status === "pending") return "text-amber-600 dark:text-amber-400";
  if (status === "processing") return "text-sky-600 dark:text-sky-400";
  if (status === "retry") return "text-orange-600 dark:text-orange-400";
  if (status === "dead") return "text-red-600 dark:text-red-400";
  if (status === "sent") return "text-emerald-600 dark:text-emerald-400";
  return "text-zinc-600 dark:text-zinc-400";
}

function outboxCount(items: OutboxStatusEntry[], status: string): number {
  return items.find((it) => it.status === status)?.count ?? 0;
}

export default function AdminSyncPage() {
  const { allowed: isAdmin } = useRoleGuard(["admin"]);

  const { data, error, isLoading, mutate } = useSWR(
    isAdmin ? ["admin-sync-status"] : null,
    () => adminSyncStatus(),
    { refreshInterval: 10_000 }, // 10초마다 자동 갱신
  );
  const {
    data: runsData,
    error: runsError,
    mutate: mutateRuns,
  } = useSWR(
    isAdmin ? ["admin-sync-runs"] : null,
    () => adminSyncRuns(12),
    { refreshInterval: 10_000 },
  );
  const {
    data: outboxData,
    error: outboxError,
    mutate: mutateOutbox,
  } = useSWR(
    isAdmin ? ["admin-sync-outbox"] : null,
    () => adminOutboxStatus(),
    { refreshInterval: 10_000 },
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
        }${full ? " (full)" : ""} · run ${res.run_id}`,
      );
      // 즉시 한번 갱신, 그 후 SWR refreshInterval로 추적
      setTimeout(() => {
        void mutate();
        void mutateRuns();
      }, 1500);
    } catch (e) {
      setMsg(`실패: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const drainOutbox = async (): Promise<void> => {
    setBusy("_outbox");
    setMsg(null);
    try {
      const res = await adminOutboxDrain(20);
      setMsg(
        `Outbox ${
          res.status === "started" ? "처리 시작" : "이미 실행 중"
        }${res.run_id ? ` · run ${res.run_id}` : ""}`,
      );
      setTimeout(() => {
        void mutateOutbox();
      }, 1500);
    } catch (e) {
      setMsg(`실패: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const staleFullItems = data?.items.filter((it) =>
    isFullStale(it.last_full_synced_at),
  ) ?? [];
  const runningRun = runsData?.items.find((it) => it.status === "running");
  const outboxItems = outboxData?.items ?? [];
  const activeOutboxCount =
    outboxCount(outboxItems, "pending") +
    outboxCount(outboxItems, "processing") +
    outboxCount(outboxItems, "retry");
  const deadOutboxCount = outboxCount(outboxItems, "dead");

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">Sync 관리</h1>
        <p className="mt-1 text-sm text-zinc-500">
          백업 데이터 동기화 — 정기 full reconcile은 매일 KST 03:00, outbox drain은
          5분마다 실행됩니다.
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

      {outboxData && (
        <div className="rounded-md border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-950">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold">Outbox</h2>
              <p className="mt-1 text-xs text-zinc-500">
                노션 반영 대기 {activeOutboxCount}건
                {deadOutboxCount > 0 ? ` · 실패 ${deadOutboxCount}건` : ""}
              </p>
            </div>
            <button
              type="button"
              onClick={() => void drainOutbox()}
              disabled={busy !== null}
              className="rounded border border-zinc-300 px-3 py-1.5 text-sm font-medium hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
            >
              {busy === "_outbox" ? "실행 중..." : "즉시 처리"}
            </button>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-5">
            {OUTBOX_STATUSES.map((status) => {
              const item = outboxItems.find((it) => it.status === status);
              return (
                <div
                  key={status}
                  className="rounded border border-zinc-200 px-3 py-2 dark:border-zinc-800"
                  title={
                    item?.oldest_created_at
                      ? formatTime(item.oldest_created_at)
                      : ""
                  }
                >
                  <div className="text-xs text-zinc-500">
                    {outboxLabel(status)}
                  </div>
                  <div
                    className={`mt-1 text-lg font-semibold tabular-nums ${outboxClass(
                      status,
                    )}`}
                  >
                    {item?.count ?? 0}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {isLoading && <LoadingState />}
      {error && (
        <div className="rounded-md border border-red-500/40 bg-red-500/5 p-3 text-sm text-red-600 dark:text-red-400">
          상태 조회 실패: {error instanceof Error ? error.message : String(error)}
        </div>
      )}
      {runsError && (
        <div className="rounded-md border border-red-500/40 bg-red-500/5 p-3 text-sm text-red-600 dark:text-red-400">
          실행 이력 조회 실패:{" "}
          {runsError instanceof Error ? runsError.message : String(runsError)}
        </div>
      )}
      {outboxError && (
        <div className="rounded-md border border-red-500/40 bg-red-500/5 p-3 text-sm text-red-600 dark:text-red-400">
          Outbox 조회 실패:{" "}
          {outboxError instanceof Error ? outboxError.message : String(outboxError)}
        </div>
      )}

      {staleFullItems.length > 0 && (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-sm text-amber-700 dark:text-amber-300">
          full reconcile 지연 감지:{" "}
          {staleFullItems
            .map((it) => KIND_LABEL[it.kind] ?? it.kind)
            .slice(0, 6)
            .join(", ")}
          {staleFullItems.length > 6 && ` 외 ${staleFullItems.length - 6}개`}
        </div>
      )}

      {runningRun && (
        <div className="rounded-md border border-sky-500/40 bg-sky-500/5 p-3 text-sm text-sky-700 dark:text-sky-300">
          실행 중: {runTarget(runningRun)}
          {runningRun.full ? " full" : " incremental"} · run{" "}
          {runningRun.run_id} · {relativeTime(runningRun.started_at)}
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

      {runsData && (
        <div className="overflow-x-auto rounded-md border border-zinc-200 dark:border-zinc-800">
          <table className="w-full text-sm">
            <thead className="bg-zinc-100 dark:bg-zinc-900">
              <tr className="text-left">
                <th className="px-3 py-2 font-medium">run</th>
                <th className="px-3 py-2 font-medium">출처</th>
                <th className="px-3 py-2 font-medium">대상</th>
                <th className="px-3 py-2 font-medium">모드</th>
                <th className="px-3 py-2 font-medium">상태</th>
                <th className="px-3 py-2 font-medium">시작</th>
                <th className="px-3 py-2 text-right font-medium">소요</th>
                <th className="px-3 py-2 font-medium">결과</th>
              </tr>
            </thead>
            <tbody>
              {runsData.items.map((it) => {
                const detail = it.error || it.result || "";
                return (
                  <tr
                    key={it.run_id}
                    className="border-t border-zinc-200 dark:border-zinc-800"
                  >
                    <td className="px-3 py-2 font-mono text-xs">
                      {it.run_id}
                    </td>
                    <td className="px-3 py-2">{sourceLabel(it.source)}</td>
                    <td className="px-3 py-2">{runTarget(it)}</td>
                    <td className="px-3 py-2">
                      {it.full ? "full" : "incremental"}
                    </td>
                    <td
                      className={`px-3 py-2 font-medium ${statusClass(
                        it.status,
                      )}`}
                    >
                      {statusLabel(it.status)}
                    </td>
                    <td className="px-3 py-2 text-zinc-600 dark:text-zinc-400">
                      {formatTime(it.started_at)}
                      <span className="ml-1 text-[10px] text-zinc-400">
                        {relativeTime(it.started_at)}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {formatElapsed(it.elapsed_seconds)}
                    </td>
                    <td className="max-w-sm truncate px-3 py-2" title={detail}>
                      {detail ? (
                        <span
                          className={
                            it.error
                              ? "text-red-600 dark:text-red-400"
                              : "text-zinc-500 dark:text-zinc-400"
                          }
                        >
                          {detail}
                        </span>
                      ) : (
                        <span className="text-zinc-400">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
              {runsData.items.length === 0 && (
                <tr>
                  <td
                    colSpan={8}
                    className="border-t border-zinc-200 px-3 py-6 text-center text-zinc-500 dark:border-zinc-800"
                  >
                    실행 이력이 없습니다.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-[11px] text-zinc-500">
        ※ 표는 10초마다 자동 갱신. sync는 fire-and-forget으로 진행 — 결과는 위
        시각/건수가 갱신되면 완료. 정기 cron은 backend HTTP trigger만 호출합니다.
      </p>
    </div>
  );
}
