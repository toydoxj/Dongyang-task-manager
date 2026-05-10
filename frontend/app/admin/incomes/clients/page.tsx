"use client";

import { useMemo, useState } from "react";

import { useAuth } from "@/components/AuthGuard";
import UnauthorizedRedirect from "@/components/UnauthorizedRedirect";
import ClientFormModal from "@/components/admin/ClientFormModal";
import LoadingState from "@/components/ui/LoadingState";
import type { Client } from "@/lib/domain";
import { useCashflow, useClients, useProjects } from "@/lib/hooks";

interface ClientRow {
  client: Client;
  projectCount: number;
  incomeCount: number;
}

export default function ClientsAdminPage() {
  const { user } = useAuth();
  // 운영(발주처) — admin + manager. 사이드바 노출과 정합 맞춤.
  const allowed = user?.role === "admin" || user?.role === "manager";
  const { data: clientData, mutate } = useClients(allowed);
  const { data: projectsData } = useProjects(undefined, allowed);
  const { data: incomeData } = useCashflow({ flow: "income" }, allowed);

  const [query, setQuery] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<string>("");
  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<Client | null>(null);

  // 사용 통계 (프로젝트의 발주처 + 수금의 실지급 모두 집계)
  const usageById = useMemo(() => {
    const proj = new Map<string, number>();
    const inc = new Map<string, number>();
    for (const p of projectsData?.items ?? []) {
      for (const cid of p.client_relation_ids ?? []) {
        proj.set(cid, (proj.get(cid) ?? 0) + 1);
      }
    }
    for (const e of incomeData?.items ?? []) {
      for (const rid of e.payer_relation_ids ?? []) {
        inc.set(rid, (inc.get(rid) ?? 0) + 1);
      }
    }
    return { proj, inc };
  }, [projectsData, incomeData]);

  const rows: ClientRow[] = useMemo(() => {
    const list = clientData?.items ?? [];
    return list.map((c) => ({
      client: c,
      projectCount: usageById.proj.get(c.id) ?? 0,
      incomeCount: usageById.inc.get(c.id) ?? 0,
    }));
  }, [clientData, usageById]);

  const categories = useMemo(() => {
    const s = new Set<string>();
    for (const r of rows) if (r.client.category) s.add(r.client.category);
    return Array.from(s).sort();
  }, [rows]);

  const filtered = rows.filter((r) => {
    if (categoryFilter && r.client.category !== categoryFilter) return false;
    if (query) {
      const q = query.toLowerCase();
      if (
        !r.client.name.toLowerCase().includes(q) &&
        !(r.client.category ?? "").toLowerCase().includes(q)
      )
        return false;
    }
    return true;
  });

  if (user && !allowed) {
    return (
      <UnauthorizedRedirect
        message="발주처 관리 권한이 없습니다."
        targetPath="/"
      />
    );
  }

  const loading = !clientData;

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">발주처 관리</h1>
          <p className="mt-1 text-sm text-zinc-500">
            노션 발주처(협력업체) DB 관리. 프로젝트·수금에서 사용 중인 발주처는
            삭제 불가.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setCreateOpen(true)}
          className="rounded-md bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
        >
          + 신규 등록
        </button>
      </header>

      <section className="rounded-xl border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900">
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
          <FilterField label="검색">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className={inputCls}
              placeholder="이름 / 구분"
            />
          </FilterField>
          <FilterField label="구분">
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className={inputCls}
            >
              <option value="">전체</option>
              {categories.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </FilterField>
        </div>
      </section>

      {loading ? (
        <LoadingState message="발주처 목록 불러오는 중" height="h-64" />
      ) : (
        <section className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
          <div className="border-b border-zinc-200 px-4 py-2 text-xs text-zinc-500 dark:border-zinc-800">
            {filtered.length}건 (전체 {rows.length})
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="border-b border-zinc-200 bg-zinc-50 text-zinc-500 dark:border-zinc-800 dark:bg-zinc-950">
                <tr>
                  <Th>이름</Th>
                  <Th className="w-32">구분</Th>
                  <Th className="w-24 text-right">프로젝트</Th>
                  <Th className="w-24 text-right">수금 건수</Th>
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 ? (
                  <tr>
                    <td
                      colSpan={4}
                      className="px-4 py-12 text-center text-xs text-zinc-400"
                    >
                      해당 발주처가 없습니다
                    </td>
                  </tr>
                ) : (
                  filtered.map((r) => (
                    <tr
                      key={r.client.id}
                      onClick={() => setEditTarget(r.client)}
                      className="cursor-pointer border-b border-zinc-100 transition-colors hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-800/40"
                    >
                      <Td className="font-medium">{r.client.name}</Td>
                      <Td className="text-zinc-500">
                        {r.client.category || "—"}
                      </Td>
                      <Td className="text-right font-mono">
                        {r.projectCount}
                      </Td>
                      <Td className="text-right font-mono">
                        {r.incomeCount}
                      </Td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <ClientFormModal
        client={null}
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSaved={() => void mutate()}
      />
      <ClientFormModal
        client={editTarget}
        open={!!editTarget}
        onClose={() => setEditTarget(null)}
        onSaved={() => void mutate()}
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
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <td className={`px-3 py-2 ${className ?? ""}`}>{children}</td>;
}
