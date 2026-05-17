"use client";

import { useMemo, useState } from "react";

import UnauthorizedRedirect from "@/components/UnauthorizedRedirect";
import LoadingState from "@/components/ui/LoadingState";
import type { Contract } from "@/lib/domain";
import { useClients, useContracts, useProjects } from "@/lib/hooks";
import { useRoleGuard } from "@/lib/useRoleGuard";
import { cn } from "@/lib/utils";

import ContractDetailDrawer from "@/components/contracts/ContractDetailDrawer";
import ContractCreateModal from "@/components/contracts/ContractCreateModal";

type SortKey = "signed_date" | "project_code" | "client_name" | "amount";
type SortDir = "asc" | "desc";

const KRW = (n: number | null | undefined): string => {
  if (n == null) return "—";
  return n.toLocaleString("ko-KR") + "원";
};

const formatDate = (s: string | null): string => {
  if (!s) return "—";
  return s.replace(/-/g, ".").slice(0, 10);
};

const formatPeriod = (
  start: string | null,
  end: string | null,
): string => {
  if (!start && !end) return "—";
  return `${formatDate(start)} ~ ${formatDate(end)}`;
};

function SortableTh({
  k,
  label,
  align = "left",
  sortKey,
  sortDir,
  onChange,
}: {
  k: SortKey;
  label: string;
  align?: "left" | "right";
  sortKey: SortKey;
  sortDir: SortDir;
  onChange: (k: SortKey) => void;
}): React.ReactElement {
  const active = sortKey === k;
  const arrow = active ? (sortDir === "asc" ? "▲" : "▼") : "⇅";
  return (
    <th
      onClick={() => onChange(k)}
      className={cn(
        "select-none cursor-pointer px-2 py-2 hover:text-zinc-700 dark:hover:text-zinc-200",
        align === "right" && "text-right",
      )}
    >
      {label}
      <span className={cn("ml-1 text-[9px]", !active && "text-zinc-300 dark:text-zinc-600")}>
        {arrow}
      </span>
    </th>
  );
}

export default function ContractsAdminPage() {
  // PR-FH/2: CUD 권한 admin/team_lead/manager. 사이드바 노출은 별도 PR에서 갱신.
  const { user, allowed } = useRoleGuard(["admin", "team_lead", "manager"]);

  const [searchQuery, setSearchQuery] = useState("");
  const [clientFilter, setClientFilter] = useState<string>("");
  const [yearFilter, setYearFilter] = useState<string>("");
  const [sortKey, setSortKey] = useState<SortKey>("signed_date");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [editing, setEditing] = useState<Contract | null>(null);
  const [creating, setCreating] = useState(false);

  // 전체 list — 1차에서는 client-side 검색/정렬 (운영 N=수백 예상, 페이지네이션 불요).
  const { data, error, mutate } = useContracts(undefined, allowed);
  const { data: clientsData } = useClients(allowed);
  const { data: projectsData } = useProjects(undefined, allowed);

  const clientNameById = useMemo(() => {
    const m = new Map<string, string>();
    for (const c of clientsData?.items ?? []) m.set(c.id, c.name);
    return m;
  }, [clientsData]);

  // 정렬 가능한 발주처 list (필터 select용)
  const clientOptions = useMemo(() => {
    const items = clientsData?.items ?? [];
    return [...items].sort((a, b) => a.name.localeCompare(b.name, "ko"));
  }, [clientsData]);

  // 사용 가능한 연도 (signed_date 있는 row 중) — desc
  const yearOptions = useMemo(() => {
    const set = new Set<number>();
    for (const c of data?.items ?? []) {
      if (c.signed_date) set.add(parseInt(c.signed_date.slice(0, 4), 10));
    }
    return [...set].sort((a, b) => b - a);
  }, [data]);

  const handleSortChange = (k: SortKey): void => {
    if (sortKey === k) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(k);
      setSortDir("desc");
    }
  };

  const filteredAndSorted = useMemo(() => {
    const items = data?.items ?? [];
    const q = searchQuery.trim().toLowerCase();
    let out = items;
    if (q) {
      out = out.filter((c) => {
        const haystack = [
          c.title,
          c.file_name ?? "",
          c.project_code ?? "",
          c.project_name ?? "",
          c.client_name ?? "",
          c.note,
        ]
          .join(" ")
          .toLowerCase();
        return haystack.includes(q);
      });
    }
    if (clientFilter) {
      out = out.filter((c) => c.client_id === clientFilter);
    }
    if (yearFilter) {
      const y = parseInt(yearFilter, 10);
      out = out.filter(
        (c) => c.signed_date && parseInt(c.signed_date.slice(0, 4), 10) === y,
      );
    }

    const dir = sortDir === "asc" ? 1 : -1;
    return [...out].sort((a, b) => {
      switch (sortKey) {
        case "signed_date": {
          if (!a.signed_date && !b.signed_date) return 0;
          if (!a.signed_date) return 1;
          if (!b.signed_date) return -1;
          return a.signed_date.localeCompare(b.signed_date) * dir;
        }
        case "project_code": {
          const ac = a.project_code ?? "";
          const bc = b.project_code ?? "";
          return ac.localeCompare(bc, "ko") * dir;
        }
        case "client_name": {
          const an = a.client_name ?? "";
          const bn = b.client_name ?? "";
          return an.localeCompare(bn, "ko") * dir;
        }
        case "amount":
          return ((a.amount ?? -Infinity) - (b.amount ?? -Infinity)) * dir;
      }
    });
  }, [data, searchQuery, clientFilter, yearFilter, sortKey, sortDir]);

  if (user && !allowed) {
    return (
      <UnauthorizedRedirect
        message="계약서 관리 권한이 없습니다."
        targetPath="/"
      />
    );
  }

  const totalAmount = (data?.items ?? []).reduce(
    (s, c) => s + (c.amount ?? 0),
    0,
  );

  return (
    <div className="space-y-4 p-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">계약서 관리</h1>
          <p className="mt-1 text-sm text-zinc-500">
            프로젝트별 계약서 메타와 PDF 파일을 통합 관리합니다.
            {totalAmount > 0 && (
              <span className="ml-2 text-emerald-700 dark:text-emerald-400">
                총 계약금액 합계{" "}
                <span className="font-mono">{KRW(totalAmount)}</span>
              </span>
            )}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setCreating(true)}
          className="rounded-md bg-zinc-900 px-3 py-1.5 text-xs text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
        >
          + 새 계약서
        </button>
      </header>

      {/* 필터 + 검색 */}
      <div className="flex flex-wrap items-center gap-2 rounded-md border border-zinc-200 bg-white p-2 dark:border-zinc-800 dark:bg-zinc-900">
        <input
          type="search"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="제목 / 파일명 / CODE / 용역명 / 발주처 / 메모"
          className="flex-1 min-w-[16rem] rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
        />
        <select
          value={clientFilter}
          onChange={(e) => setClientFilter(e.target.value)}
          className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
        >
          <option value="">발주처 전체</option>
          {clientOptions.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <select
          value={yearFilter}
          onChange={(e) => setYearFilter(e.target.value)}
          className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
        >
          <option value="">연도 전체</option>
          {yearOptions.map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </select>
        {data && (
          <span className="shrink-0 text-[11px] text-zinc-500">
            {searchQuery || clientFilter || yearFilter
              ? `${filteredAndSorted.length} / ${data.items.length} 건`
              : `${data.items.length} 건`}
          </span>
        )}
      </div>

      {error && (
        <div className="rounded-md border border-red-500/40 bg-red-500/5 p-3 text-sm text-red-400">
          {error instanceof Error ? error.message : String(error)}
        </div>
      )}

      {data == null ? (
        <LoadingState message="계약서 목록 불러오는 중" height="h-32" />
      ) : filteredAndSorted.length === 0 ? (
        <p className="rounded-md border border-zinc-200 bg-white p-4 text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900">
          계약서가 없습니다.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-md border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
          <table className="w-full min-w-[900px] text-sm">
            <thead>
              <tr className="border-b border-zinc-200 text-left text-[11px] uppercase text-zinc-500 dark:border-zinc-800">
                <SortableTh
                  k="signed_date"
                  label="계약일"
                  sortKey={sortKey}
                  sortDir={sortDir}
                  onChange={handleSortChange}
                />
                <SortableTh
                  k="project_code"
                  label="CODE"
                  sortKey={sortKey}
                  sortDir={sortDir}
                  onChange={handleSortChange}
                />
                <th className="px-2 py-2">용역명 / 계약서명</th>
                <SortableTh
                  k="client_name"
                  label="발주처"
                  sortKey={sortKey}
                  sortDir={sortDir}
                  onChange={handleSortChange}
                />
                <th className="px-2 py-2">계약기간</th>
                <SortableTh
                  k="amount"
                  label="계약금액"
                  align="right"
                  sortKey={sortKey}
                  sortDir={sortDir}
                  onChange={handleSortChange}
                />
                <th className="px-2 py-2 text-center">PDF</th>
              </tr>
            </thead>
            <tbody>
              {filteredAndSorted.map((c) => (
                <tr
                  key={c.id}
                  onClick={() => setEditing(c)}
                  className="cursor-pointer border-b border-zinc-100 hover:bg-zinc-50 dark:border-zinc-900 dark:hover:bg-zinc-800/50"
                >
                  <td className="px-2 py-2 text-xs text-zinc-700 dark:text-zinc-300">
                    {formatDate(c.signed_date)}
                  </td>
                  <td className="px-2 py-2 font-mono text-[11px] text-zinc-500">
                    {c.project_code || "—"}
                  </td>
                  <td className="px-2 py-2">
                    <div className="font-medium">{c.project_name || "—"}</div>
                    <div className="mt-0.5 text-[11px] text-zinc-500">
                      {c.title}
                      {c.vat_included && (
                        <span className="ml-1 rounded bg-amber-500/10 px-1 text-[9px] text-amber-700">
                          VAT 포함
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-2 py-2 text-xs text-zinc-700 dark:text-zinc-300">
                    {c.client_name ||
                      (c.client_id ? clientNameById.get(c.client_id) ?? "—" : "—")}
                  </td>
                  <td className="px-2 py-2 text-xs text-zinc-600 dark:text-zinc-400">
                    {formatPeriod(c.start_date, c.end_date)}
                  </td>
                  <td className="px-2 py-2 text-right font-mono text-xs">
                    {KRW(c.amount)}
                  </td>
                  <td className="px-2 py-2 text-center">
                    {c.drive_url ? (
                      <a
                        href={c.drive_url}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="rounded bg-blue-500/10 px-2 py-0.5 text-[10px] text-blue-700 hover:bg-blue-500/20 dark:text-blue-400"
                        title={c.file_name ?? ""}
                      >
                        다운로드
                      </a>
                    ) : (
                      <span className="text-[10px] text-zinc-400">미첨부</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ContractCreateModal
        open={creating}
        projects={projectsData?.items ?? []}
        onClose={() => setCreating(false)}
        onCreated={() => {
          setCreating(false);
          void mutate();
        }}
      />
      <ContractDetailDrawer
        contract={editing}
        onClose={() => setEditing(null)}
        onChanged={() => void mutate()}
      />
    </div>
  );
}
