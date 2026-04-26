"use client";

import { useEffect, useState } from "react";

import { useAuth } from "@/components/AuthGuard";
import RevenueCollectionChart from "@/components/dashboard/RevenueCollectionChart";
import StageBoard from "@/components/dashboard/StageBoard";
import { getCashflow, listProjects } from "@/lib/api";
import type { CashflowEntry, Project } from "@/lib/domain";

export default function DashboardPage() {
  const { user } = useAuth();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [incomes, setIncomes] = useState<CashflowEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const [pr, cf] = await Promise.all([
          listProjects(),
          getCashflow({ flow: "income" }),
        ]);
        setProjects(pr.items);
        setIncomes(cf.items);
      } catch (err) {
        setError(err instanceof Error ? err.message : "데이터 로딩 실패");
      }
    })();
  }, []);

  const loading = projects == null || incomes == null;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">대시보드</h1>
        <p className="mt-1 text-sm text-zinc-500">
          {user?.name || user?.username} 님 환영합니다.
        </p>
      </header>

      {error && (
        <div className="rounded-md border border-red-500/40 bg-red-500/5 p-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {loading && !error && (
        <div className="space-y-3">
          <SkeletonCard />
          <SkeletonCard h="h-[480px]" />
        </div>
      )}

      {projects && incomes && (
        <>
          <section>
            <h2 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
              월별 매출/수금 추이
            </h2>
            <RevenueCollectionChart projects={projects} incomes={incomes} />
          </section>

          <section>
            <h2 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
              진행단계별 보드
            </h2>
            <StageBoard projects={projects} />
          </section>
        </>
      )}
    </div>
  );
}

function SkeletonCard({ h = "h-72" }: { h?: string }) {
  return (
    <div
      className={`${h} animate-pulse rounded-xl border border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900`}
    />
  );
}
