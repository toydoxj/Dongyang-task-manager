"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/components/AuthGuard";
import CashflowForecast from "@/components/dashboard/CashflowForecast";
import EmployeeLoadHeatmap from "@/components/dashboard/EmployeeLoadHeatmap";
import ExpenseTrend from "@/components/dashboard/ExpenseTrend";
import RevenueCollectionChart from "@/components/dashboard/RevenueCollectionChart";
import StageBoard from "@/components/dashboard/StageBoard";
import StaleTaskAlert from "@/components/dashboard/StaleTaskAlert";
import TeamLoadHeatmap from "@/components/dashboard/TeamLoadHeatmap";
import WorkTypeTreemap from "@/components/dashboard/WorkTypeTreemap";
import LoadingState from "@/components/ui/LoadingState";
import { useCashflow, useProjects, useTasks } from "@/lib/hooks";

export default function DashboardPage() {
  const { user } = useAuth();
  const router = useRouter();

  // 대시보드는 관리자/팀장 전용 — 일반 직원이 URL로 들어오면 내 업무로 redirect
  const allowed = user?.role === "admin" || user?.role === "team_lead";
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

  if (!user || !allowed) return null;

  const error = projectErr ?? cashflowErr;
  const projects = projectData?.items;
  const incomes = cashflowData?.items;
  const expenses = expenseData?.items;
  const allTasks = tasksData?.items;
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
      <header>
        <h1 className="text-2xl font-semibold">대시보드</h1>
        <p className="mt-1 text-sm text-zinc-500">
          {user?.name || user?.username} 님 환영합니다.
        </p>
      </header>

      {error && (
        <div className="rounded-md border border-red-500/40 bg-red-500/5 p-3 text-sm text-red-400">
          {error instanceof Error ? error.message : String(error)}
        </div>
      )}

      {loading && !error && (
        <LoadingState
          message="대시보드 데이터 불러오는 중 (프로젝트 1,500+ / 수금 1,900+)"
          height="h-96"
        />
      )}

      {projects && incomes && (
        <>
          <section>
            <h2 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
              월별 수주 / 수금 / 지출 추이
            </h2>
            <RevenueCollectionChart
              projects={projects}
              incomes={incomes}
              expenses={expenses ?? []}
            />
          </section>

          <section>
            <h2 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
              진행단계별 보드
            </h2>
            <StageBoard projects={projects} />
          </section>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <section>
              <h2 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
                팀별 부하
              </h2>
              <TeamLoadHeatmap projects={projects} />
            </section>
            <section>
              <h2 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
                직원별 부하
              </h2>
              <EmployeeLoadHeatmap projects={projects} />
            </section>
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <section>
              <h2 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
                업무유형 매출 (전체)
              </h2>
              <WorkTypeTreemap
                projects={projects}
                title="업무유형 매출 — 전체"
                subtitle="누적 전체"
              />
            </section>
            <section>
              <h2 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
                업무유형 매출 (최근 1년)
              </h2>
              <WorkTypeTreemap
                projects={recentYearProjects}
                title="업무유형 매출 — 최근 1년"
                subtitle="시작일 기준 최근 12개월"
              />
            </section>
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <section>
              <h2 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
                현금흐름 예측 (향후 12개월)
              </h2>
              <CashflowForecast projects={projects} />
            </section>
            <section>
              <h2 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
                지출 구분 월간 추이
              </h2>
              {expenses ? (
                <ExpenseTrend expenses={expenses} />
              ) : (
                <LoadingState message="지출 데이터 분석 중" height="h-64" />
              )}
            </section>
          </div>

          {allTasks && allTasks.length > 0 && (
            <section>
              <h2 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
                업무 적체 알림
              </h2>
              <StaleTaskAlert tasks={allTasks} />
            </section>
          )}
        </>
      )}
    </div>
  );
}
