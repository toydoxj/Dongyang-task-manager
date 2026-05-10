"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

import { useAuth } from "@/components/AuthGuard";
import UnauthorizedRedirect from "@/components/UnauthorizedRedirect";
import SalesEditModal from "@/components/sales/SalesEditModal";
import SalesTable from "@/components/sales/SalesTable";
import LoadingState from "@/components/ui/LoadingState";
import { BID_STAGES, type Sale } from "@/lib/domain";
import { useSales } from "@/lib/hooks";

const KIND_FILTERS = [
  { label: "전체", value: "" },
  { label: "수주영업", value: "수주영업" },
  { label: "기술지원", value: "기술지원" },
] as const;

export default function SalesPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useAuth();
  // 운영(영업) — admin + manager. 사이드바 노출과 정합 맞춤.
  const allowed = user?.role === "admin" || user?.role === "manager";
  const [kindFilter, setKindFilter] = useState<string>("");
  const [stageFilter, setStageFilter] = useState<string>("");
  // 두 source를 통합해 modal에 전달:
  //   ① URL ?sale={id} (외부 진입 — 주간보고/프로젝트 상세 등 referrer)
  //   ② 사용자가 list row 클릭
  // useMemo로 derived — effect 내 setState 제거.
  const [clickedSale, setClickedSale] = useState<Sale | null>(null);
  const [creating, setCreating] = useState(false);

  const filters = {
    ...(kindFilter ? { kind: kindFilter } : {}),
    ...(stageFilter ? { stage: stageFilter } : {}),
  };
  const { data, error } = useSales(filters, allowed);

  const queriedSaleId = searchParams.get("sale");
  const editing = useMemo<Sale | null>(() => {
    // URL이 있으면 URL 우선. data 로드 전이면 null.
    if (queriedSaleId) {
      return data?.items.find((s) => s.id === queriedSaleId) ?? null;
    }
    return clickedSale;
  }, [queriedSaleId, data, clickedSale]);

  if (user && !allowed) {
    return (
      <UnauthorizedRedirect
        message="영업 관리 권한이 없습니다."
        targetPath="/"
      />
    );
  }

  return (
    <div className="space-y-4">
      <header className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">영업 파이프라인</h1>
          <p className="mt-1 text-sm text-zinc-500">
            수주영업(견적·입찰) + 기술지원(수주 전 자문). 기대매출 = 견적금액 × 단계별 수주확률.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setCreating(true)}
          className="rounded-md bg-zinc-900 px-3 py-1.5 text-xs text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
        >
          + 새 영업
        </button>
      </header>

      {/* 필터 */}
      <div className="flex flex-wrap items-center gap-2 rounded-md border border-zinc-200 bg-white p-2 dark:border-zinc-800 dark:bg-zinc-900">
        <span className="text-[11px] text-zinc-500">유형:</span>
        {KIND_FILTERS.map((k) => (
          <button
            key={k.value}
            type="button"
            onClick={() => setKindFilter(k.value)}
            className={
              kindFilter === k.value
                ? "rounded bg-zinc-900 px-2 py-0.5 text-[11px] text-white dark:bg-zinc-100 dark:text-zinc-900"
                : "rounded border border-zinc-300 px-2 py-0.5 text-[11px] hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
            }
          >
            {k.label}
          </button>
        ))}
        <span className="ml-3 text-[11px] text-zinc-500">단계:</span>
        <button
          type="button"
          onClick={() => setStageFilter("")}
          className={
            stageFilter === ""
              ? "rounded bg-zinc-900 px-2 py-0.5 text-[11px] text-white dark:bg-zinc-100 dark:text-zinc-900"
              : "rounded border border-zinc-300 px-2 py-0.5 text-[11px] hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
          }
        >
          전체
        </button>
        {BID_STAGES.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setStageFilter(s)}
            className={
              stageFilter === s
                ? "rounded bg-zinc-900 px-2 py-0.5 text-[11px] text-white dark:bg-zinc-100 dark:text-zinc-900"
                : "rounded border border-zinc-300 px-2 py-0.5 text-[11px] hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
            }
          >
            {s}
          </button>
        ))}
      </div>

      {error && (
        <div className="rounded-md border border-red-500/40 bg-red-500/5 p-3 text-sm text-red-400">
          {error instanceof Error ? error.message : String(error)}
        </div>
      )}

      {data == null ? (
        <LoadingState message="영업 목록 불러오는 중" height="h-32" />
      ) : (
        <SalesTable sales={data.items} onClickRow={setClickedSale} />
      )}

      <SalesEditModal
        sale={editing}
        openNew={creating}
        onClose={() => {
          setClickedSale(null);
          setCreating(false);
          // referrer가 같이 넘어왔으면 (예: 주간 업무일지) 그 페이지로 복귀.
          // 그렇지 않은 경우엔 ?sale= query만 제거 (refresh 후 useEffect 재트리거 방지).
          const fromPath = searchParams.get("from");
          if (fromPath && fromPath.startsWith("/")) {
            router.push(fromPath);
          } else if (queriedSaleId) {
            router.replace("/sales", { scroll: false });
          }
        }}
      />
    </div>
  );
}
