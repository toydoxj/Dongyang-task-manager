"use client";

import { useState } from "react";

import CashflowForecast from "@/components/dashboard/CashflowForecast";
import EmployeeLoadHeatmap from "@/components/dashboard/EmployeeLoadHeatmap";
import ExpenseTrend from "@/components/dashboard/ExpenseTrend";
import RecentAndStaleProjects from "@/components/dashboard/RecentAndStaleProjects";
import RecentUpdatesPanel from "@/components/dashboard/RecentUpdatesPanel";
import RevenueCollectionChart from "@/components/dashboard/RevenueCollectionChart";
import StageBoard from "@/components/dashboard/StageBoard";
import StaleTaskAlert from "@/components/dashboard/StaleTaskAlert";
import TeamLoadHeatmap from "@/components/dashboard/TeamLoadHeatmap";
import WarningItemsPanel from "@/components/dashboard/WarningItemsPanel";
import WorkTypeTreemap from "@/components/dashboard/WorkTypeTreemap";
import LoadingState from "@/components/ui/LoadingState";
import type { CashflowEntry, Project, Task } from "@/lib/domain";

type TabKey = "risk" | "load" | "revenue" | "stage";

const TABS: { key: TabKey; label: string; hint: string }[] = [
  { key: "risk", label: "운영 리스크", hint: "정체·적체 알림" },
  { key: "load", label: "인력 부하", hint: "팀별·직원별" },
  { key: "revenue", label: "매출·수금", hint: "월별 추이 + 현금흐름" },
  { key: "stage", label: "단계 현황", hint: "진행단계 + 업무유형" },
];

interface Props {
  projects: Project[];
  incomes: CashflowEntry[];
  expenses: CashflowEntry[];
  allTasks: Task[] | undefined;
  recentYearProjects: Project[];
}

/** DASH-003 — 9개 차트 컴포넌트를 4개 탭으로 그룹화. */
export default function ChartsTabs({
  projects,
  incomes,
  expenses,
  allTasks,
  recentYearProjects,
}: Props) {
  const [active, setActive] = useState<TabKey>("risk");

  return (
    <section className="space-y-3">
      <nav
        aria-label="차트 영역 탭"
        className="flex flex-wrap items-center gap-2 border-b border-zinc-200 dark:border-zinc-800"
      >
        {TABS.map((t) => {
          const isActive = active === t.key;
          return (
            <button
              key={t.key}
              type="button"
              onClick={() => setActive(t.key)}
              title={t.hint}
              className={
                isActive
                  ? "-mb-px border-b-2 border-zinc-900 px-3 py-1.5 text-sm font-semibold text-zinc-900 dark:border-zinc-100 dark:text-zinc-100"
                  : "px-3 py-1.5 text-sm font-medium text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
              }
            >
              {t.label}
            </button>
          );
        })}
      </nav>

      {active === "risk" && (
        <div className="space-y-4">
          <RecentAndStaleProjects projects={projects} />
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <WarningItemsPanel projects={projects} />
            <RecentUpdatesPanel projects={projects} />
          </div>
          {allTasks && allTasks.length > 0 && <StaleTaskAlert tasks={allTasks} />}
        </div>
      )}

      {active === "load" && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Subsection title="팀별 부하">
            <TeamLoadHeatmap projects={projects} />
          </Subsection>
          <Subsection title="직원별 부하">
            <EmployeeLoadHeatmap projects={projects} />
          </Subsection>
        </div>
      )}

      {active === "revenue" && (
        <div className="space-y-4">
          <Subsection title="월별 수주 / 수금 / 지출 추이">
            <RevenueCollectionChart
              projects={projects}
              incomes={incomes}
              expenses={expenses}
            />
          </Subsection>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Subsection title="현금흐름 예측 (향후 12개월)">
              <CashflowForecast projects={projects} />
            </Subsection>
            <Subsection title="지출 구분 월간 추이">
              {expenses.length > 0 ? (
                <ExpenseTrend expenses={expenses} />
              ) : (
                <LoadingState message="지출 데이터 분석 중" height="h-64" />
              )}
            </Subsection>
          </div>
        </div>
      )}

      {active === "stage" && (
        <div className="space-y-4">
          <Subsection title="진행단계별 보드">
            <StageBoard projects={projects} />
          </Subsection>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Subsection title="업무유형 매출 (전체)">
              <WorkTypeTreemap
                projects={projects}
                title="업무유형 매출 — 전체"
                subtitle="누적 전체"
              />
            </Subsection>
            <Subsection title="업무유형 매출 (최근 1년)">
              <WorkTypeTreemap
                projects={recentYearProjects}
                title="업무유형 매출 — 최근 1년"
                subtitle="시작일 기준 최근 12개월"
              />
            </Subsection>
          </div>
        </div>
      )}
    </section>
  );
}

function Subsection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h3 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
        {title}
      </h3>
      {children}
    </section>
  );
}
