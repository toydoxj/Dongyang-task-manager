"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";

import { useAuth } from "@/components/AuthGuard";
import LoadingState from "@/components/ui/LoadingState";
import { listEmployees } from "@/lib/api";
import { cn } from "@/lib/utils";

export default function EmployeeWorkSelectorPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [q, setQ] = useState("");

  const allowed = user?.role === "admin" || user?.role === "team_lead";
  useEffect(() => {
    if (user && !allowed) router.replace("/me");
  }, [user, allowed, router]);

  const { data, error, isLoading } = useSWR(
    allowed ? ["employees", "active"] : null,
    () => listEmployees(undefined, "active"),
  );
  const employees = useMemo(() => {
    const items = data?.items ?? [];
    if (!q) return items;
    const lower = q.toLowerCase();
    return items.filter(
      (e) =>
        e.name.toLowerCase().includes(lower) ||
        (e.team ?? "").toLowerCase().includes(lower) ||
        (e.position ?? "").toLowerCase().includes(lower),
    );
  }, [data, q]);

  if (!user || !allowed) return null;

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">직원 업무</h1>
        <p className="mt-1 text-sm text-zinc-500">
          직원을 선택하면 해당 직원이 보는 「내 업무」 화면을 동일하게 표시합니다.
          (관리자/팀장 전용)
        </p>
      </header>

      <input
        type="search"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="이름, 팀, 직급으로 검색..."
        className="w-full max-w-md rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm outline-none dark:border-zinc-700 dark:bg-zinc-950"
      />

      {error && (
        <p className="rounded-md border border-red-500/40 bg-red-500/5 p-3 text-sm text-red-400">
          {error instanceof Error ? error.message : "직원 명부 로드 실패"}
        </p>
      )}

      {isLoading && !data ? (
        <LoadingState message="직원 명부 불러오는 중" height="h-32" />
      ) : (
        <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {employees.map((e) => (
            <li key={e.id}>
              <Link
                href={`/me?as=${encodeURIComponent(e.name)}`}
                className={cn(
                  "block rounded-lg border border-zinc-200 bg-white px-3 py-2.5 text-sm transition-colors hover:bg-zinc-50",
                  "dark:border-zinc-800 dark:bg-zinc-900 dark:hover:bg-zinc-800",
                )}
              >
                <p className="font-medium">{e.name}</p>
                <p className="mt-0.5 text-[11px] text-zinc-500">
                  {[e.team, e.position].filter(Boolean).join(" · ") || "—"}
                </p>
              </Link>
            </li>
          ))}
          {employees.length === 0 && data && (
            <li className="col-span-full text-center text-xs text-zinc-500">
              {q ? "검색 결과가 없습니다" : "활성 직원이 없습니다"}
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
