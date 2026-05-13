// /api/weekly-report — 주간 업무일지 조회/PDF/발행/last-published (PR-W ~ PR-AD)
import { authFetch, downloadPdfBlob } from "./_internal";

export interface WeeklyHeadcount {
  total: number;
  by_occupation: Record<string, number>;
  by_team: Record<string, number>;
  new_this_week: number;
  resigned_this_week: string[];
}

export interface WeeklySalesItem {
  page_id: string;
  code: string;
  category: string[];
  name: string;
  client: string;
  scale: string;
  estimated_amount: number | null;
  /** 수주확률 0~100 (PM 직접 입력). */
  probability: number | null;
  is_bid: boolean;
  stage: string;
  submission_date: string | null;
  sales_start_date: string | null;     // 영업시작일 (PR-W)
}

export interface WeeklyCompletedItem {
  page_id: string;
  code: string;
  name: string;
  teams: string[];
  assignees: string[];
  client: string;
  status_label: string;
  completed_at: string | null;
  /** 수주확정일. 소요기간 산정 기준. */
  started_at: string | null;
  /** 소요기간(개월) — (end - start)/30, 소수 1자리. */
  duration_months: number | null;
}

export interface WeeklyNewProject {
  page_id: string;
  code: string;
  name: string;
  teams: string[];
  assignees: string[];
  client: string;
  work_types: string[];
  scale: string;
  contract_amount: number | null;
  stage: string;
  started_at: string | null;
}

export interface WeeklyTeamProjectRow {
  code: string;
  name: string;
  client: string;
  pm: string;
  stage: string;
  progress: number;
  weekly_plan: string;
  note: string;
  assignees: string[];
  end_date: string | null;
}

export interface WeeklyEmployeeWorkRow {
  employee_name: string;
  position: string;
  kind: "project" | "sale";  // 프로젝트=파랑, 영업=초록
  source_id: string;         // mirror_projects/sales의 page_id (상세 link용)
  project_code: string;
  project_name: string;
  client: string;
  stage: string;            // 운영 stage (정렬용 — UI는 phase 표시)
  phase: string;            // 작업단계 — 업무일지 "진행단계" 컬럼
  last_week_summary: string;
  this_week_plan: string;
  note: string;
}

export interface WeeklyTeamMember {
  name: string;
  position: string;
  team: string;
  sort_order: number;
}

export interface WeeklyHoliday {
  date: string;       // YYYY-MM-DD
  name: string;
  source: "legal" | "company";
}

export interface WeeklySuggestionLog {
  title: string;
  author: string;
  status: string;
  created_at: string | null;
}

export interface WeeklyStageProject {
  page_id: string;
  code: string;
  name: string;
  client: string;
  teams: string[];
  is_long_stalled: boolean;
}

export interface WeeklySealLogItem {
  project_id: string;            // 프로젝트 page_id (상세 link용)
  code: string;
  name: string;
  submission_target: string;
  seal_type: string;
  requester: string;
  approved_at: string | null;
}

export interface WeeklyPersonalScheduleEntry {
  employee_name: string;
  team: string;
  category: string;
  kind: "project" | "sale" | "other";   // 색상 분류
  start_date: string;
  end_date: string;
  note: string;
  project_code: string;
}

export interface WeeklyReport {
  period_start: string;
  period_end: string;
  headcount: WeeklyHeadcount;
  notices: string[];
  education: string[];
  seal_log: WeeklySealLogItem[];
  completed: WeeklyCompletedItem[];
  new_projects: WeeklyNewProject[];
  sales: WeeklySalesItem[];
  personal_schedule: WeeklyPersonalScheduleEntry[];
  teams: Record<string, WeeklyTeamProjectRow[]>;
  team_work: Record<string, WeeklyEmployeeWorkRow[]>;
  team_members: Record<string, WeeklyTeamMember[]>;
  holidays: WeeklyHoliday[];
  suggestions: WeeklySuggestionLog[];
  waiting_projects: WeeklyStageProject[];
  on_hold_projects: WeeklyStageProject[];
}

export interface WeeklyReportRange {
  weekStart: string;            // 이번주 시작일 (월요일 권장)
  weekEnd?: string;             // optional — default: weekStart + 4일
  lastWeekStart?: string;       // optional — default: weekStart - 7일
}

function buildWeeklyReportQuery(
  range: WeeklyReportRange,
  forceRefresh = false,
): string {
  const sp = new URLSearchParams({ week_start: range.weekStart });
  if (range.weekEnd) sp.set("week_end", range.weekEnd);
  if (range.lastWeekStart) sp.set("last_week_start", range.lastWeekStart);
  if (forceRefresh) sp.set("force_refresh", "true");
  return sp.toString();
}

export async function fetchWeeklyReport(
  range: WeeklyReportRange,
  options: { forceRefresh?: boolean } = {},
): Promise<WeeklyReport> {
  const res = await authFetch(
    `/api/weekly-report?${buildWeeklyReportQuery(range, options.forceRefresh)}`,
  );
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      (detail as { detail?: string } | null)?.detail ??
        `${res.status} ${res.statusText}`,
    );
  }
  return (await res.json()) as WeeklyReport;
}

export async function downloadWeeklyReportPdf(
  range: WeeklyReportRange,
  options: { forceRefresh?: boolean } = {},
): Promise<void> {
  await downloadPdfBlob(
    `/api/weekly-report.pdf?${buildWeeklyReportQuery(range, options.forceRefresh)}`,
    `${range.weekStart}_업무일지.pdf`,
  );
}

/** 주간 업무일지 PDF를 Blob으로 가져옴 (iframe 미리보기용).
 * 호출자가 URL.createObjectURL로 변환해 사용하고, 사용 후 revokeObjectURL 책임. */
export async function fetchWeeklyReportPdfBlob(
  range: WeeklyReportRange,
  options: { forceRefresh?: boolean } = {},
): Promise<Blob> {
  const res = await authFetch(
    `/api/weekly-report.pdf?${buildWeeklyReportQuery(range, options.forceRefresh)}`,
  );
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      (detail as { detail?: string } | null)?.detail ??
        `${res.status} ${res.statusText}`,
    );
  }
  return await res.blob();
}

// 발행 (admin only) — WORKS Drive 업로드 + 전직원 알림 + 발행 로그 저장
export interface PublishWeeklyReportResponse {
  file_id: string;
  file_url: string;
  file_name: string;
  recipient_count: number;
  notify_failed_count: number;
  log_id: number;
}

export async function publishWeeklyReport(
  range: WeeklyReportRange,
): Promise<PublishWeeklyReportResponse> {
  const body: Record<string, string | undefined> = {
    week_start: range.weekStart,
    week_end: range.weekEnd,
    last_week_start: range.lastWeekStart,
  };
  const res = await authFetch(`/api/weekly-report/publish`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      (detail as { detail?: string } | null)?.detail ??
        `${res.status} ${res.statusText}`,
    );
  }
  return (await res.json()) as PublishWeeklyReportResponse;
}

export interface LastPublishedWeeklyReport {
  week_start: string | null;
  week_end: string | null;
  published_at: string | null;
}

export async function fetchLastPublishedWeeklyReport(): Promise<LastPublishedWeeklyReport> {
  const res = await authFetch(`/api/weekly-report/last-published`);
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      (detail as { detail?: string } | null)?.detail ??
        `${res.status} ${res.statusText}`,
    );
  }
  return (await res.json()) as LastPublishedWeeklyReport;
}

/** 가장 최근 발행된 PDF 다운로드 (비admin용). 브라우저 다운로드 trigger. */
export async function downloadLastPublishedWeeklyReportPdf(): Promise<void> {
  const res = await authFetch(`/api/weekly-report/last-published.pdf`);
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      (detail as { detail?: string } | null)?.detail ??
        `${res.status} ${res.statusText}`,
    );
  }
  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") ?? "";
  // filename*=UTF-8''<quoted> 또는 filename="..."
  let filename = "주간업무일지.pdf";
  const m1 = cd.match(/filename\*=UTF-8''([^;]+)/);
  const m2 = cd.match(/filename="?([^";]+)"?/);
  if (m1) filename = decodeURIComponent(m1[1]);
  else if (m2) filename = m2[1];
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
