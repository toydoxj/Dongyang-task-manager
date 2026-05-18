"use client";

import { useMemo, useState } from "react";

import UnauthorizedRedirect from "@/components/UnauthorizedRedirect";
import LoadingState from "@/components/ui/LoadingState";
import { downloadContractFile } from "@/lib/api";
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
  // PR-FI/6: 「계약체크 + 미등록」 가상 row 클릭 시 등록 모달에 projectId prefill.
  const [createInitialProjectId, setCreateInitialProjectId] = useState<string>("");
  const [createKey, setCreateKey] = useState(0);

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

  // PR-FI/6: contract_signed=True이지만 Contract row 0건인 프로젝트는 가상 row로 추가.
  // ContractOut shape으로 stub (id < 0 으로 가상 표시).
  const virtualRows = useMemo<Contract[]>(() => {
    const items = data?.items ?? [];
    const projects = projectsData?.items ?? [];
    if (projects.length === 0) return [];
    const projectsWithContract = new Set(items.map((c) => c.project_id));
    const missing = projects.filter(
      (p) => p.contract_signed && !projectsWithContract.has(p.id),
    );
    return missing.map((p, idx) => {
      const cid = p.client_relation_ids?.[0] ?? null;
      return {
        id: -(idx + 1),
        project_id: p.id,
        title: "",
        signed_date: null,
        start_date: p.contract_start ?? null,
        end_date: p.contract_end ?? null,
        amount: p.contract_amount ?? null,
        vat_included: false,
        drive_file_id: null,
        drive_url: null,
        file_name: null,
        uploaded_at: null,
        note: "",
        created_by: null,
        created_at: "",
        updated_at: "",
        project_code: p.code,
        project_name: p.name,
        client_id: cid,
        client_name: cid ? clientNameById.get(cid) ?? null : null,
      } as Contract;
    });
  }, [data, projectsData, clientNameById]);

  const filteredAndSorted = useMemo(() => {
    const items = [...(data?.items ?? []), ...virtualRows];
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
  }, [data, virtualRows, searchQuery, clientFilter, yearFilter, sortKey, sortDir]);

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

  const openCreateForProject = (projectId: string): void => {
    setCreateInitialProjectId(projectId);
    setCreateKey((k) => k + 1);
    setCreating(true);
  };

  const openCreateBlank = (): void => {
    setCreateInitialProjectId("");
    setCreateKey((k) => k + 1);
    setCreating(true);
  };

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
          onClick={openCreateBlank}
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
              {filteredAndSorted.map((c) => {
                const isVirtual = c.id < 0;
                return (
                  <tr
                    key={isVirtual ? `virtual-${c.project_id}` : c.id}
                    onClick={() =>
                      isVirtual ? openCreateForProject(c.project_id) : setEditing(c)
                    }
                    className={cn(
                      "cursor-pointer border-b border-zinc-100 hover:bg-zinc-50 dark:border-zinc-900 dark:hover:bg-zinc-800/50",
                      isVirtual &&
                        "bg-amber-500/5 hover:bg-amber-500/10 dark:bg-amber-500/10 dark:hover:bg-amber-500/15",
                    )}
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
                        {isVirtual ? (
                          <span className="text-amber-700 dark:text-amber-400">
                            ⚠ 계약체크는 되어있지만 계약서가 등록되지 않음 — 클릭해 등록
                          </span>
                        ) : (
                          <>
                            {c.title}
                            {c.vat_included && (
                              <span className="ml-1 rounded bg-amber-500/10 px-1 text-[9px] text-amber-700">
                                VAT 포함
                              </span>
                            )}
                          </>
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
                        <button
                          type="button"
                          onClick={async (e) => {
                            e.stopPropagation();
                            try {
                              await downloadContractFile(
                                c.id,
                                c.file_name || `contract_${c.id}`,
                              );
                            } catch (err) {
                              alert(err instanceof Error ? err.message : "다운로드 실패");
                            }
                          }}
                          className="rounded bg-blue-500/10 px-2 py-0.5 text-[10px] text-blue-700 hover:bg-blue-500/20 dark:text-blue-400"
                          title={c.file_name ?? ""}
                        >
                          다운로드
                        </button>
                      ) : (
                        <span className="text-[10px] text-zinc-400">
                          {isVirtual ? "미등록" : "미첨부"}
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <ContractCreateModal
        key={createKey}
        open={creating}
        projects={projectsData?.items ?? []}
        initialProjectId={createInitialProjectId}
        onClose={() => setCreating(false)}
        onCreated={() => {
          setCreating(false);
          void mutate();
        }}
      />
      <ContractDetailDrawer
        // PR-GB: contract.drive_url을 key에 포함 → 파일 업로드/삭제 시 modal 자체
        //   force-remount. Body 내부 useState 초기값이 prop을 받는 패턴이라
        //   prop 갱신만으론 일부 cell이 stale로 남는 케이스 방어.
        //   사용자가 메타 편집 중 업로드하면 입력값 reset되지만 (드물고 직관적).
        key={editing ? `${editing.id}-${editing.drive_url ?? "no"}` : "closed"}
        contract={editing}
        onClose={() => setEditing(null)}
        onChanged={(updated) => {
          void mutate();
          // PR-GA: 모달의 contract prop을 즉시 갱신해 drive_url 등 stale view 회피.
          if (updated) setEditing(updated);
        }}
      />
    </div>
  );
}
