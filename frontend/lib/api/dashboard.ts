// /api/dashboard — 대시보드 KPI/액션 backend 집계 (PR-BJ Phase 4-F)
import { authFetch, jsonOrThrow } from "./_internal";

export interface TopTeam {
  name: string;
  count: number;
}

export interface DashboardSummary {
  in_progress_count: number;
  stalled_count: number;
  due_soon_tasks: number;
  pending_seal_count: number;
  week_income: number;
  week_expense: number;
  top_team: TopTeam | null;
  /** 검증용 — backend가 사용한 KST 기준일 */
  today: string;
  week_start: string;
  week_end: string;
}

export async function fetchDashboardSummary(): Promise<DashboardSummary> {
  const res = await authFetch("/api/dashboard/summary");
  return jsonOrThrow<DashboardSummary>(res);
}
