"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";

import { useAuth } from "@/components/AuthGuard";
import LoadingState from "@/components/ui/LoadingState";
import {
  listSealRequests,
  type SealRequestItem,
} from "@/lib/api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

import DetailModal from "./_DetailModal";
import { STATUS_TABS, STATUS_COLOR, type StatusTab } from "./_utils";

export default function SealRequestsPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const isAdminOrLead = isAdmin || user?.role === "team_lead";
  const myName = user?.name || user?.username || "";

  const [tab, setTab] = useState<StatusTab>("전체");
  const [selected, setSelected] = useState<SealRequestItem | null>(null);

  // hooks는 early return 이전에 모두 호출 (rules-of-hooks)
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


