"use client";

import { useMemo, useState } from "react";

import { useAuth } from "@/components/AuthGuard";
import IncomeFormModal from "@/components/admin/IncomeFormModal";
import LoadingState from "@/components/ui/LoadingState";
import type { CashflowEntry, Project } from "@/lib/domain";
import { formatWon } from "@/lib/format";
import { useCashflow, useProjects } from "@/lib/hooks";

interface IncomeRow {
  entry: CashflowEntry;
  project: Project | null;
  projectName: string;
  projectCode: string;
  payerName: string;
  cumulativeRate: number; // 0~1, 해당 row까지 누적 수금률
}

export default function IncomesAdminPage() {
  const { user } = useAuth();
  const { data: projectsData } = useProjects(undefined, user?.role === "admin");
  const { data: cashflowData, mutate } = useCashflow(
    { flow: "income" },
    user?.role === "admin",
  );

  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [projectQuery, setProjectQuery] = useState("");
  const [payerQuery, setPayerQuery] = useState("");
  const [editTarget, setEditTarget] = useState<CashflowEntry | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  const projectMap = useMemo(() => {
    const map = new Map<string, Project>();
    for (const p of projectsData?.items ?? []) map.set(p.id, p);
    return map;
  }, [projectsData]);

  const rows: IncomeRow[] = useMemo(() => {
    const items = cashflowData?.items ?? [];
    // 1) 모든 income을 date asc로 정렬해 프로젝트별 누적합 계산
    const sorted = items
      .filter((e) => e.type === "income")
      .slice()
      .sort((a, b) => (a.date ?? "").localeCompare(b.date ?? ""));
    const cumByProject = new Map<string, number>();
    const rateById = new Map<string, number>();
    for (const e of sorted) {
      const pid = e.project_ids[0] ?? "";
      const prev = cumByProject.get(pid) ?? 0;
      const next = prev + e.amount;
      cumByProject.set(pid, next);
      const project = pid ? projectMap.get(pid) : undefined;
      const denom = project
        ? (project.contract_amount ?? 0) + (project.vat ?? 0)
        : 0;
      rateById.set(e.id, denom > 0 ? next / denom : 0);
    }

    return sorted.map((e) => {
      const pid = e.project_ids[0] ?? "";
      const project = pid ? projectMap.get(pid) ?? null : null;
      return {
        entry: e,
        project,
        projectName: project?.name ?? "(미연결)",
        projectCode: project?.code ?? "",
        payerName: e.payer_names?.[0] ?? "",
        cumulativeRate: rateById.get(e.id) ?? 0,
      };
    });
  }, [cashflowData, projectMap]);

  // 필터 적용
  const filtered = rows.filter((r) => {
    const d = r.entry.date?.slice(0, 10) ?? "";
    if (dateFrom && d && d < dateFrom) return false;
    if (dateTo && d && d > dateTo) return false;
    if (projectQuery) {
      const q = projectQuery.toLowerCase();
      if (
        !r.projectName.toLowerCase().includes(q) &&
        !r.projectCode.toLowerCase().includes(q)
      )
        return false;
    }
    if (payerQuery) {
      const q = payerQuery.toLowerCase();
      if (!r.payerName.toLowerCase().includes(q)) return false;
    }
    return true;
  });

  // 보드는 desc 정렬이 자연스러움 (최신 위)
  const visible = filtered.slice().reverse();
  const totalAmount = filtered.reduce((s, r) => s + r.entry.amount, 0);

  if (user && user.role !== "admin") {
    return (
      <main className="p-6">
        <p className="text-sm text-red-500">관리자 권한이 필요합니다.</p>
      </main>
    );
  }

  const loading = !cashflowData || !projectsData;

  const exportCsv = (): void => {
    const header = [
      "수금일",
      "Sub_CODE",
      "프로젝트명",
      "실지급",
      "회차",
      "금액",
      "누적수금률(%)",
      "비고",
    ];
    const lines = [header.join(",")];
    for (const r of visible) {
      const cells = [
        r.entry.date ?? "",
        r.projectCode,
        r.projectName,
        r.payerName,
        r.entry.round_no?.toString() ?? "",
        r.entry.amount.toString(),
        (r.cumulativeRate * 100).toFixed(1),
        (r.entry.note ?? "").replace(/[\n,]/g, " "),
      ];
      lines.push(cells.map((c) => `"${c}"`).join(","));
    }
    const blob = new Blob(["﻿" + lines.join("\n")], {
      type: "text/csv;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `incomes_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">수금 관리</h1>
          <p className="mt-1 text-sm text-zinc-500">
            노션 수금 DB의 일자별 일지. 신규 등록·편집·삭제 가능 (관리자 전용).
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={exportCsv}
            className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
          >
            CSV
          </button>
          <button
            type="button"
            onClick={() => setCreateOpen(true)}
            className="rounded-md bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
          >
            + 신규 등록
          </button>
        </div>
      </header>

      <section className="rounded-xl border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <FilterField label="시작일">
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className={inputCls}
            />
          </FilterField>
          <FilterField label="종료일">
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className={inputCls}
            />
          </FilterField>
          <FilterField label="프로젝트">
            <input
              type="text"
              value={projectQuery}
              onChange={(e) => setProjectQuery(e.target.value)}
              className={inputCls}
              placeholder="이름 / Sub CODE"
            />
          </FilterField>
          <FilterField label="실지급">
            <input
              type="text"
              value={payerQuery}
              onChange={(e) => setPayerQuery(e.target.value)}
              className={inputCls}
              placeholder="발주처명"
            />
          </FilterField>
        </div>
      </section>

      {loading ? (
        <LoadingState message="수금 데이터 불러오는 중" height="h-64" />
      ) : (
        <section className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
          <div className="flex items-center justify-between border-b border-zinc-200 px-4 py-2 text-xs dark:border-zinc-800">
            <span className="text-zinc-500">{visible.length}건</span>
            <span className="font-medium">
              합계 <span className="ml-1">{formatWon(totalAmount)}</span>
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="border-b border-zinc-200 bg-zinc-50 text-zinc-500 dark:border-zinc-800 dark:bg-zinc-950">
                <tr>
                  <Th className="w-24">일자</Th>
                  <Th className="w-20 text-right">회차</Th>
                  <Th>프로젝트</Th>
                  <Th>실지급</Th>
                  <Th className="text-right">금액</Th>
                  <Th className="w-24 text-right">누적 수금률</Th>
                  <Th>비고</Th>
                </tr>
              </thead>
              <tbody>
                {visible.length === 0 ? (
                  <tr>
                    <td
                      colSpan={7}
                      className="px-4 py-12 text-center text-xs text-zinc-400"
                    >
                      해당 데이터가 없습니다
                    </td>
                  </tr>
                ) : (
                  visible.map((r) => (
                    <tr
                      key={r.entry.id}
                      onClick={() => setEditTarget(r.entry)}
                      className="cursor-pointer border-b border-zinc-100 transition-colors hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-800/40"
                    >
                      <Td className="font-mono text-[11px]">
                        {r.entry.date?.slice(0, 10) ?? "—"}
                      </Td>
                      <Td className="text-right">
                        {r.entry.round_no ?? "—"}
                      </Td>
                      <Td>
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-[10px] text-zinc-500">
                            {r.projectCode || "—"}
                          </span>
                          <span className="truncate" title={r.projectName}>
                            {r.projectName}
                          </span>
                        </div>
                      </Td>
                      <Td className="truncate" title={r.payerName}>
                        {r.payerName || "—"}
                      </Td>
                      <Td className="text-right font-medium">
                        {formatWon(r.entry.amount)}
                      </Td>
                      <Td className="text-right">
                        <RateBadge rate={r.cumulativeRate} />
                      </Td>
                      <Td
                        className="truncate text-zinc-500"
                        title={r.entry.note}
                      >
                        {r.entry.note || ""}
                      </Td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <IncomeFormModal
        entry={null}
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSaved={() => void mutate()}
        projects={projectsData?.items ?? []}
      />
      <IncomeFormModal
        entry={editTarget}
        open={!!editTarget}
        onClose={() => setEditTarget(null)}
        onSaved={() => void mutate()}
        projects={projectsData?.items ?? []}
      />
    </div>
  );
}

const inputCls =
  "w-full rounded-md border border-zinc-300 bg-white px-2.5 py-1.5 text-sm outline-none focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-950";

function FilterField({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-[10px] text-zinc-500">{label}</span>
      {children}
    </label>
  );
}

function Th({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <th
      className={`px-3 py-2 text-left font-medium ${className ?? ""}`}
      scope="col"
    >
      {children}
    </th>
  );
}

function Td({
  children,
  className,
  title,
}: {
  children: React.ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <td className={`px-3 py-2 ${className ?? ""}`} title={title}>
      {children}
    </td>
  );
}

function RateBadge({ rate }: { rate: number }) {
  const pct = (rate * 100).toFixed(1);
  let color = "text-zinc-500";
  if (rate >= 1) color = "text-emerald-500";
  else if (rate >= 0.5) color = "text-blue-500";
  else if (rate > 0) color = "text-amber-500";
  return <span className={`font-mono ${color}`}>{pct}%</span>;
}
