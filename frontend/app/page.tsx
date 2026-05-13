"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/components/AuthGuard";
import ChartsTabs from "@/components/dashboard/ChartsTabs";
import KPICards from "@/components/dashboard/KPICards";
import PriorityActionsPanel from "@/components/dashboard/PriorityActionsPanel";
import LoadingState from "@/components/ui/LoadingState";
import {
  useCashflow,
  useDashboardSummary,
  useProjects,
  useSealRequests,
  useTasks,
} from "@/lib/hooks";

export default function DashboardPage() {
  const { user } = useAuth();
  const router = useRouter();

  // 대시보드는 관리자/팀장/관리팀 — 일반 직원이 URL로 들어오면 내 업무로 redirect
  const allowed =
    user?.role === "admin" ||
    user?.role === "team_lead" ||
    user?.role === "manager";
  useEffect(() => {
    if (user && !allowed) router.replace("/me");
  }, [user, allowed, router]);

  const { data: projectData, error: projectErr } = useProjects(undefined, allowed);
  const { data: cashflowData, error: cashflowErr } = useCashflow(
    { flow: "income" },
    allowed,
  );
  const { data: expenseData } = useCashflow({ flow: "expense" }, allowed);
  const { data: tasksData } = useTasks(undefined, allowed);
  const { data: sealData } = useSealRequests(undefined, allowed);
  // PR-BJ-2: KPI는 backend 집계 endpoint 사용. ChartsTabs/PriorityActionsPanel 등
  // 다른 컴포넌트는 PR-BJ-3~5에서 점진 전환 — 그 동안 list endpoint도 유지.
  const { data: summary } = useDashboardSummary(allowed);

  if (!user || !allowed) return null;

  const error = projectErr ?? cashflowErr;
  const projects = projectData?.items;
  const incomes = cashflowData?.items;
  const expenses = expenseData?.items;
  const allTasks = tasksData?.items;
  const sealRequests = sealData?.items;
  const loading = !projects || !incomes;

  // 최근 1년 (시작일 기준)
  const oneYearAgo = new Date();
  oneYearAgo.setFullYear(oneYearAgo.getFullYear() - 1);
  const recentYearProjects = (projects ?? []).filter((p) => {
    if (!p.start_date) return false;
    return new Date(p.start_date) >= oneYearAgo;
  });

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">대시보드</h1>
          <p className="mt-1 text-sm text-zinc-500">
            {user?.name || user?.username} 님 환영합니다.
          </p>
        </div>
        <Link
          href="/weekly-report"
          className="rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-700"
        >
          주간업무일지 보기
        </Link>
      </header>

      {error && (
        <div className="rounded-md border border-red-500/40 bg-red-500/5 p-3 text-sm text-red-400">
          {error instanceof Error ? error.message : String(error)}
        </div>
      )}

      {loading && !error && (
        <LoadingState
          message="대시보드 데이터 불러오는 중"
          height="h-96"
        />
      )}

      {projects && incomes && (
        <>
          {summary && (
            <KPICards
              summary={summary}
              sealRequests={sealRequests ?? []}
            />
          )}

          <PriorityActionsPanel
            projects={projects}
            tasks={allTasks ?? []}
            sealRequests={sealRequests ?? []}
          />

          <ChartsTabs
            projects={projects}
            incomes={incomes}
            expenses={expenses ?? []}
            allTasks={allTasks}
            recentYearProjects={recentYearProjects}
          />
        </>
      )}
    </div>
  );
}
