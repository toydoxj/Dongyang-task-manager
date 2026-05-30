"use client";

/**
 * /admin/auth-stats — 인증 채널 모니터링 (admin only).
 *
 * Phase 4-G 5차 재시도(cookie 단독 인증 전환) go/no-go 판단용.
 * backend `_auth_channel_counts` in-memory 누적 카운터를 admin endpoint로 조회.
 *
 * - cookie_ready_ratio ≥ 0.99 → 5차 go 권고 (Codex)
 * - 0.95 ≤ ratio < 0.99 → 관찰 지속
 * - ratio < 0.95 → cookie 미발급 사용자 잔존, header fallback 필요 (재시도 위험)
 *
 * Render restart 시 counter reset — since 필드로 사용자가 인지.
 * single instance(starter plan)라 multi-instance 분산 우려 없음.
 *
 * PR-ET.
 */

import useSWR from "swr";

import UnauthorizedRedirect from "@/components/UnauthorizedRedirect";
import LoadingState from "@/components/ui/LoadingState";
import { getAuthChannelStats } from "@/lib/api";
import {
  GO_THRESHOLD,
  type VerdictMeta,
  verdictForRatio,
} from "@/lib/authStatsVerdict";
import { useRoleGuard } from "@/lib/useRoleGuard";

const REFRESH_INTERVAL_MS = 30_000;

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

function relativeFrom(iso: string | null): string {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const diffMs = Date.now() - t;
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return "방금";
  if (diffMin < 60) return `${diffMin}분`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}시간`;
  const diffDay = Math.floor(diffHr / 24);
  return `${diffDay}일`;
}

const TONE_CLASS: Record<VerdictMeta["tone"], string> = {
  go: "bg-emerald-100 text-emerald-900 dark:bg-emerald-500/15 dark:text-emerald-200",
  watch: "bg-amber-100 text-amber-900 dark:bg-amber-500/15 dark:text-amber-200",
  "no-go": "bg-red-100 text-red-900 dark:bg-red-500/15 dark:text-red-200",
  idle: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
};

export default function AdminAuthStatsPage() {
  const { allowed: isAdmin } = useRoleGuard(["admin"]);

  const { data, error, isLoading, mutate } = useSWR(
    isAdmin ? ["admin-auth-stats"] : null,
    () => getAuthChannelStats(),
    { refreshInterval: REFRESH_INTERVAL_MS },
  );

  if (!isAdmin) {
    return (
      <UnauthorizedRedirect
        targetPath="/dashboard"
        message="관리자만 접근 가능합니다."
      />
    );
  }

  if (isLoading || !data) {
    return <LoadingState />;
  }

  if (error) {
    return (
      <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
        조회 실패: {error instanceof Error ? error.message : String(error)}
      </div>
    );
  }

  const headerWithValidCookie = data.header_with_valid_cookie ?? 0;
  const headerWithoutCookie = data.header_without_cookie ?? data.header;
  const headerWithInvalidCookie = data.header_with_invalid_cookie ?? 0;
  const headerWithMismatchedCookie = data.header_with_mismatched_cookie ?? 0;
  const cookieReady = data.cookie_ready ?? data.cookie;
  const cookieBlocked = data.cookie_blocked ?? data.header;
  const cookieReadinessTotal = data.cookie_readiness_total ?? data.total;
  const cookieReadyRatio = data.cookie_ready_ratio ?? data.cookie_ratio;
  const v = verdictForRatio(cookieReadyRatio, cookieReadinessTotal);
  const headerPct = data.total > 0 ? (data.header / data.total) * 100 : 0;
  const cookiePct = data.total > 0 ? (data.cookie / data.total) * 100 : 0;
  const cookieReadyPct =
    cookieReadinessTotal > 0 ? cookieReadyRatio * 100 : 0;
  const cookieBlockedPct =
    cookieReadinessTotal > 0 ? 100 - cookieReadyPct : 0;

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-lg font-bold">인증 채널 모니터링</h1>
        <p className="text-xs text-zinc-500">
          Phase 4-G 5차 재시도(cookie 단독 인증) go/no-go 판단용. header
          요청은 cookie shadow 검증까지 포함, 30초마다 자동 갱신.
        </p>
      </header>

      <section
        className={`rounded-xl border border-transparent p-4 ${TONE_CLASS[v.tone]}`}
      >
        <div className="text-sm font-semibold">{v.label}</div>
        <div className="mt-1 text-xs">{v.detail}</div>
      </section>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-lg border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900">
          <div className="text-[11px] text-zinc-500">cookie-only 통과 가능</div>
          <div className="mt-1 text-2xl font-bold text-emerald-700 dark:text-emerald-300">
            {cookieReady.toLocaleString()}
          </div>
          <div className="text-[11px] text-zinc-500">
            {cookieReadyPct.toFixed(2)}% · 권장: ≥
            {(GO_THRESHOLD * 100).toFixed(0)}%
          </div>
        </div>
        <div className="rounded-lg border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900">
          <div className="text-[11px] text-zinc-500">cookie-only 차단</div>
          <div className="mt-1 text-2xl font-bold text-red-700 dark:text-red-300">
            {cookieBlocked.toLocaleString()}
          </div>
          <div className="text-[11px] text-zinc-500">
            {cookieBlockedPct.toFixed(2)}% · cookie 없음/무효
          </div>
        </div>
        <div className="rounded-lg border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900">
          <div className="text-[11px] text-zinc-500">현재 header 채널</div>
          <div className="mt-1 text-2xl font-bold text-amber-700 dark:text-amber-300">
            {data.header.toLocaleString()}
          </div>
          <div className="text-[11px] text-zinc-500">
            {headerPct.toFixed(2)}% · localStorage token fallback
          </div>
        </div>
        <div className="rounded-lg border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900">
          <div className="text-[11px] text-zinc-500">전체 인증 호출</div>
          <div className="mt-1 text-2xl font-bold">
            {data.total.toLocaleString()}
          </div>
          <div className="text-[11px] text-zinc-500">누적 집계</div>
        </div>
      </section>

      {cookieReadinessTotal > 0 && (
        <section className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
          <div className="mb-2 text-xs font-medium text-zinc-700 dark:text-zinc-200">
            cookie-only 준비도
          </div>
          <div className="h-4 w-full overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
            <div
              className="h-full bg-emerald-500"
              style={{ width: `${cookieReadyPct}%` }}
              title={`cookie-only 통과 가능 ${cookieReadyPct.toFixed(2)}%`}
            />
          </div>
          <div className="mt-1 flex items-center justify-between text-[10px] text-zinc-500">
            <span>통과 가능 {cookieReadyPct.toFixed(2)}%</span>
            <span>차단 {cookieBlockedPct.toFixed(2)}%</span>
          </div>
        </section>
      )}

      {data.total > 0 && (
        <section className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
          <div className="mb-3 text-xs font-medium text-zinc-700 dark:text-zinc-200">
            header 요청 shadow 검증
          </div>
          <div className="grid gap-2 sm:grid-cols-4">
            <div>
              <div className="text-[10px] text-zinc-500">valid cookie</div>
              <div className="text-base font-semibold text-emerald-700 dark:text-emerald-300">
                {headerWithValidCookie.toLocaleString()}
              </div>
            </div>
            <div>
              <div className="text-[10px] text-zinc-500">cookie 없음</div>
              <div className="text-base font-semibold text-red-700 dark:text-red-300">
                {headerWithoutCookie.toLocaleString()}
              </div>
            </div>
            <div>
              <div className="text-[10px] text-zinc-500">cookie 무효</div>
              <div className="text-base font-semibold text-red-700 dark:text-red-300">
                {headerWithInvalidCookie.toLocaleString()}
              </div>
            </div>
            <div>
              <div className="text-[10px] text-zinc-500">사용자 불일치</div>
              <div className="text-base font-semibold text-red-700 dark:text-red-300">
                {headerWithMismatchedCookie.toLocaleString()}
              </div>
            </div>
          </div>
          <div className="mt-3 border-t border-zinc-200 pt-3 text-[10px] text-zinc-500 dark:border-zinc-800">
            현재 우선 채널: cookie {cookiePct.toFixed(2)}% / header{" "}
            {headerPct.toFixed(2)}%
          </div>
        </section>
      )}

      <section className="rounded-xl border border-zinc-200 bg-white p-4 text-xs text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
        <div className="font-medium text-zinc-700 dark:text-zinc-200">
          누적 시작: {formatTime(data.since)}
          {data.since && (
            <span className="ml-1 text-zinc-500">
              (약 {relativeFrom(data.since)} 전)
            </span>
          )}
        </div>
        <div className="mt-2 space-y-1">
          <p>
            ※ Render restart 시 카운터 reset 됩니다. since가 너무 짧으면
            (수십분 이내) 표본이 부족할 수 있으니 운영 1주 이상 관찰 권장.
          </p>
          <p>
            ※ 같은 사용자가 자주 호출하면 ratio가 왜곡됩니다 — 다양한 사용자
            활동 패턴을 포함한 누적이 필요.
          </p>
        </div>
      </section>

      <div className="flex justify-end">
        <button
          onClick={() => void mutate()}
          className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800"
        >
          새로고침
        </button>
      </div>
    </div>
  );
}
