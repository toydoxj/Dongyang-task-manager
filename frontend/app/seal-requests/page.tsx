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
import {
  STATUS_TABS,
  STATUS_COLOR,
  type StatusTab,
} from "./_utils";

const INITIAL_LIMIT = 25;

function fallbackText(value: string | null | undefined): string {
  return value?.trim() || "미지정";
}

function realSourceLabel(item: SealRequestItem): string {
  return fallbackText(item.real_source_name);
}

export default function SealRequestsPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const isAdminOrLead = isAdmin || user?.role === "team_lead";
  const myName = user?.name || user?.username || "";

  const [tab, setTab] = useState<StatusTab>("전체");
  const [selected, setSelected] = useState<SealRequestItem | null>(null);
  const [visibleLimit, setVisibleLimit] = useState(INITIAL_LIMIT);

  // hooks는 early return 이전에 모두 호출 (rules-of-hooks)
  const { data, error, isLoading, mutate } = useSWR(
    user && isAdminOrLead ? ["seal-requests", visibleLimit] : null,
    () => listSealRequests({ limit: visibleLimit }),
  );

  const all = useMemo(() => data?.items ?? [], [data]);
  const total = data?.total ?? all.length;
  const hasMore = total > all.length;
  const counts = useMemo(() => {
    const c: Record<string, number> = { 전체: total };
    for (const s of ["1차검토 중", "2차검토 중", "승인", "반려"]) {
      c[s] = all.filter((x) => x.status === s).length;
    }
    return c;
  }, [all, total]);

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
          {total > INITIAL_LIMIT && (
            <p className="mt-1 text-xs text-zinc-400">
              먼저 {INITIAL_LIMIT}건을 불러오고 필요할 때 이어서 표시합니다.
            </p>
          )}
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
        <div className="overflow-x-auto rounded-md border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
          <table className="min-w-[980px] w-full table-fixed text-left text-sm">
            <colgroup>
              <col className="w-[90px]" />
              <col className="w-[270px]" />
              <col className="w-[220px]" />
              <col className="w-[170px]" />
              <col className="w-[90px]" />
              <col className="w-[90px]" />
              <col className="w-[120px]" />
              <col className="w-[90px]" />
            </colgroup>
            <thead className="border-b border-zinc-200 bg-zinc-50 text-xs text-zinc-500 dark:border-zinc-800 dark:bg-zinc-950/60 dark:text-zinc-400">
              <tr>
                <th className="px-3 py-2 font-medium">프로젝트번호</th>
                <th className="px-3 py-2 font-medium">프로젝트명</th>
                <th className="px-3 py-2 font-medium">발주처</th>
                <th className="px-3 py-2 font-medium">실제출처</th>
                <th className="px-3 py-2 font-medium">구분</th>
                <th className="px-3 py-2 font-medium">요청자</th>
                <th className="px-3 py-2 font-medium">제출예정일</th>
                <th className="px-3 py-2 font-medium">상태</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {filtered.map((s) => (
                <tr
                  key={s.id}
                  tabIndex={0}
                  role="button"
                  onClick={() => setSelected(s)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setSelected(s);
                    }
                  }}
                  className="cursor-pointer hover:bg-zinc-50 focus:bg-zinc-50 focus:outline-none dark:hover:bg-zinc-800/50 dark:focus:bg-zinc-800/50"
                >
                  <td className="truncate px-3 py-2 text-zinc-700 dark:text-zinc-200" title={fallbackText(s.project_code)}>
                    {fallbackText(s.project_code)}
                  </td>
                  <td className="truncate px-3 py-2 font-medium text-zinc-900 dark:text-zinc-100" title={fallbackText(s.project_name)}>
                    {fallbackText(s.project_name)}
                  </td>
                  <td className="truncate px-3 py-2 text-zinc-700 dark:text-zinc-300" title={fallbackText(s.project_client_name)}>
                    {fallbackText(s.project_client_name)}
                  </td>
                  <td className="truncate px-3 py-2 text-zinc-700 dark:text-zinc-300" title={realSourceLabel(s)}>
                    {realSourceLabel(s)}
                  </td>
                  <td className="truncate px-3 py-2 text-zinc-700 dark:text-zinc-300" title={fallbackText(s.seal_type)}>
                    {fallbackText(s.seal_type)}
                  </td>
                  <td className="truncate px-3 py-2 text-zinc-700 dark:text-zinc-300" title={fallbackText(s.requester)}>
                    {fallbackText(s.requester)}
                  </td>
                  <td className="truncate px-3 py-2 text-zinc-700 dark:text-zinc-300">
                    {formatDate(s.due_date)}
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className={cn(
                        "inline-flex rounded-md px-2 py-0.5 text-[11px] font-medium",
                        STATUS_COLOR[s.status] ?? STATUS_COLOR["1차검토 중"],
                      )}
                    >
                      {s.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {hasMore && (
        <div className="flex justify-center">
          <button
            type="button"
            onClick={() => setVisibleLimit((v) => v + INITIAL_LIMIT)}
            className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800"
          >
            더 보기 ({all.length}/{total})
          </button>
        </div>
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


