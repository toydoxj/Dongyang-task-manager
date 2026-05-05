"use client";

import { useState } from "react";

import SalesEditModal from "@/components/sales/SalesEditModal";
import SalesTable from "@/components/sales/SalesTable";
import LoadingState from "@/components/ui/LoadingState";
import type { Sale } from "@/lib/domain";
import { useSales } from "@/lib/hooks";

interface Props {
  /** 본인 또는 (admin/team_lead가 다른 사람 보기 시) 그 직원 이름 */
  effectiveName: string;
  /** 다른 직원 보기 모드 (=mine 사용 X, assignee 명시) */
  isViewingOther: boolean;
}

export default function MySalesSection({
  effectiveName,
  isViewingOther,
}: Props) {
  const filters = isViewingOther
    ? { assignee: effectiveName }
    : { mine: true };
  const { data, error } = useSales(filters);
  const [editing, setEditing] = useState<Sale | null>(null);
  const [creating, setCreating] = useState(false);

  const sales = data?.items ?? [];
  const bid = sales.filter((s) => s.kind === "수주영업");
  const presales = sales.filter((s) => s.kind === "기술지원");
  const other = sales.filter(
    (s) => s.kind !== "수주영업" && s.kind !== "기술지원",
  );
  const totalExpected = sales.reduce((n, s) => n + (s.expected_revenue || 0), 0);

  return (
    <section>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
          {isViewingOther ? `${effectiveName} 님의 영업` : "내 영업"} ({sales.length})
          {totalExpected > 0 && (
            <span className="text-[11px] font-normal text-emerald-700 dark:text-emerald-400">
              기대매출{" "}
              <span className="font-mono">
                {totalExpected.toLocaleString("ko-KR")}원
              </span>
            </span>
          )}
        </h2>
        <button
          type="button"
          onClick={() => setCreating(true)}
          className="rounded-md bg-zinc-900 px-2.5 py-1 text-xs text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
        >
          + 새 영업
        </button>
      </div>

      {error && (
        <div className="mb-2 rounded-md border border-red-500/40 bg-red-500/5 p-2 text-xs text-red-400">
          {error instanceof Error ? error.message : String(error)}
        </div>
      )}

      {data == null ? (
        <LoadingState message="내 영업 불러오는 중" height="h-24" />
      ) : sales.length === 0 ? (
        <p className="rounded-md border border-zinc-200 bg-white p-3 text-xs text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900">
          담당 영업이 없습니다.
        </p>
      ) : (
        <div className="space-y-4">
          {bid.length > 0 && (
            <SubGroup label="수주영업" count={bid.length} color="blue">
              <SalesTable sales={bid} onClickRow={setEditing} showKindColumn={false} />
            </SubGroup>
          )}
          {presales.length > 0 && (
            <SubGroup label="기술지원" count={presales.length} color="purple">
              <SalesTable
                sales={presales}
                onClickRow={setEditing}
                showKindColumn={false}
              />
            </SubGroup>
          )}
          {other.length > 0 && (
            <SubGroup label="유형 미설정" count={other.length} color="zinc">
              <SalesTable sales={other} onClickRow={setEditing} showKindColumn={false} />
            </SubGroup>
          )}
        </div>
      )}

      <SalesEditModal
        sale={editing}
        openNew={creating}
        defaultAssignee={effectiveName}
        onClose={() => {
          setEditing(null);
          setCreating(false);
        }}
      />
    </section>
  );
}

function SubGroup({
  label,
  count,
  color,
  children,
}: {
  label: string;
  count: number;
  color: "blue" | "purple" | "zinc";
  children: React.ReactNode;
}) {
  const dotColor =
    color === "blue"
      ? "bg-blue-500"
      : color === "purple"
        ? "bg-purple-500"
        : "bg-zinc-400";
  const textColor =
    color === "blue"
      ? "text-blue-600 dark:text-blue-400"
      : color === "purple"
        ? "text-purple-600 dark:text-purple-400"
        : "text-zinc-500";
  return (
    <div>
      <h3
        className={`mb-1 flex items-center gap-2 text-xs font-semibold ${textColor}`}
      >
        <span className={`h-2 w-2 rounded-full ${dotColor}`} />
        {label} ({count})
      </h3>
      {children}
    </div>
  );
}
