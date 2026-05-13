// 백엔드 호출 헬퍼 — 인증 토큰 자동 주입 + JSON 파싱 + 에러 메시지 통일.

import { authFetch } from "./auth";
import type {
  Project,
  QuoteFormResponse,
  QuoteInput,
  QuoteResult,
  Sale,
  SaleCreateRequest,
  SaleListResponse,
  SaleUpdateRequest,
} from "./domain";

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const detail = await res
      .json()
      .then((d) => (d as { detail?: string }).detail)
      .catch(() => undefined);
    throw new Error(detail ?? `${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}

function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

// ── 프로젝트 ── (PR-BE — lib/api/projects.ts)
export * from "./api/projects";

// ── 업무 TASK ── (Phase 4-A — lib/api/tasks.ts)
export * from "./api/tasks";

// ── Cashflow + 수금 CRUD ── (PR-BD — lib/api/cashflow.ts)
export * from "./api/cashflow";

// ── 협력업체(발주처) ── (PR-S — lib/api/clients.ts)
export * from "./api/clients";

// ── 계약 항목 ── (PR-BD — lib/api/contractItems.ts)
export * from "./api/contractItems";

// ── 마스터 프로젝트 + 이미지 CRUD ── (PR-BD — lib/api/masterProjects.ts)
export * from "./api/masterProjects";

// ── 사용자 관리 (admin) ── (PR-BD — lib/api/users.ts)
export * from "./api/users";

// ── 직원 명부 ── (PR-BD — lib/api/employees.ts)
export * from "./api/employees";

// ── WORKS Drive 임베디드 탐색기 ── (PR-BD — lib/api/drive.ts)
export * from "./api/drive";

// ── 건의사항 ── (PR-S2 — lib/api/suggestions.ts)
export * from "./api/suggestions";

// ── 날인요청 ── (PR-BE — lib/api/seals.ts)
export * from "./api/seals";


// ── 영업(Sales) ──

export async function listSales(
  filters: {
    assignee?: string;
    kind?: string;
    stage?: string;
    mine?: boolean;
  } = {},
): Promise<SaleListResponse> {
  const res = await authFetch(`/api/sales${qs(filters)}`);
  return jsonOrThrow<SaleListResponse>(res);
}

export async function getSale(pageId: string): Promise<Sale> {
  const res = await authFetch(`/api/sales/${pageId}`);
  return jsonOrThrow<Sale>(res);
}

export async function createSale(body: SaleCreateRequest): Promise<Sale> {
  const res = await authFetch(`/api/sales`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<Sale>(res);
}

export async function updateSale(
  pageId: string,
  body: SaleUpdateRequest,
): Promise<Sale> {
  const res = await authFetch(`/api/sales/${pageId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<Sale>(res);
}

export async function archiveSale(
  pageId: string,
): Promise<{ status: string; page_id: string }> {
  const res = await authFetch(`/api/sales/${pageId}`, { method: "DELETE" });
  return jsonOrThrow<{ status: string; page_id: string }>(res);
}

/** 수주영업·우선협상/낙찰 단계의 영업을 메인 프로젝트로 전환. admin 전용. */
export async function convertSale(pageId: string): Promise<Project> {
  const res = await authFetch(`/api/sales/${pageId}/convert`, { method: "POST" });
  return jsonOrThrow<Project>(res);
}

/** 영업을 기존 진행 프로젝트에 수동 연결. admin 전용.
 * 영업의 단계가 '완료'로 자동 변경되고 전환된 프로젝트 relation이 채워진다.
 */
export async function linkSaleToProject(
  pageId: string,
  projectId: string,
): Promise<Sale> {
  const res = await authFetch(`/api/sales/${pageId}/link-project`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: projectId }),
  });
  return jsonOrThrow<Sale>(res);
}

/** 프로젝트 id로 연결된 영업(Sale) reverse lookup. 없으면 null. */
export async function findSaleByProject(projectId: string): Promise<Sale | null> {
  const res = await authFetch(`/api/sales/by-project/${projectId}`);
  if (!res.ok) {
    if (res.status === 404) return null;
    throw new Error(`${res.status} ${res.statusText}`);
  }
  // backend가 null을 그대로 직렬화하면 응답이 "null" 문자열
  const body = await res.text();
  if (!body || body === "null") return null;
  return JSON.parse(body) as Sale;
}

/** 견적서 산출 미리보기 (저장 X) — 입력 변경 시 디바운스 호출. */
export async function previewQuote(input: QuoteInput): Promise<QuoteResult> {
  const res = await authFetch(`/api/sales/quote/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return jsonOrThrow<QuoteResult>(res);
}

/** 단일 견적 PDF → WORKS Drive [견적서]/{YYYY}년 자동 업로드 + 노션 sale 견적서첨부 갱신.
 * quoteId 미지정 시 첫 견적 (legacy 호환). */
export async function saveQuotePdfToDrive(
  saleId: string,
  quoteId?: string,
): Promise<Sale> {
  const qs = quoteId ? `?quote_id=${encodeURIComponent(quoteId)}` : "";
  const res = await authFetch(
    `/api/sales/${saleId}/quote/save-pdf-to-drive${qs}`,
    { method: "POST" },
  );
  return jsonOrThrow<Sale>(res);
}

/** 견적서 PDF 다운로드 — Content-Disposition filename*로 한글 파일명 자동. */
async function downloadPdfBlob(url: string, fallbackFilename: string): Promise<void> {
  const res = await authFetch(url);
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      (detail as { detail?: string } | null)?.detail ??
        `${res.status} ${res.statusText}`,
    );
  }
  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") ?? "";
  let filename = fallbackFilename;
  const star = cd.match(/filename\*=UTF-8''([^;]+)/i);
  if (star) {
    try {
      filename = decodeURIComponent(star[1]);
    } catch {
      /* fallthrough */
    }
  }
  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(blobUrl);
}

/** 단일 견적 PDF 다운로드. quoteId 미지정 시 첫 견적 (legacy 호환). */
export async function downloadQuotePdf(
  saleId: string,
  quoteId?: string,
): Promise<void> {
  const qs = quoteId ? `?quote_id=${encodeURIComponent(quoteId)}` : "";
  await downloadPdfBlob(`/api/sales/${saleId}/quote.pdf${qs}`, "quote.pdf");
}

/** 영업의 모든 견적 list (PR-M1). */
export async function listSaleQuotes(
  saleId: string,
): Promise<QuoteFormResponse[]> {
  const res = await authFetch(`/api/sales/${saleId}/quotes`);
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      (detail as { detail?: string } | null)?.detail ??
        `${res.status} ${res.statusText}`,
    );
  }
  return (await res.json()) as QuoteFormResponse[];
}

/** 영업에 견적 1건 추가 (PR-M1). suffix·doc_number 자동 부여. */
export async function addSaleQuote(
  saleId: string,
  input: QuoteInput,
): Promise<QuoteFormResponse> {
  const res = await authFetch(`/api/sales/${saleId}/quotes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      (detail as { detail?: string } | null)?.detail ??
        `${res.status} ${res.statusText}`,
    );
  }
  return (await res.json()) as QuoteFormResponse;
}

/** 견적 수정 — input/result만 갱신, doc_number/suffix 보존 (PR-M1). */
export async function updateSaleQuote(
  saleId: string,
  quoteId: string,
  input: QuoteInput,
): Promise<QuoteFormResponse> {
  const res = await authFetch(`/api/sales/${saleId}/quotes/${quoteId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      (detail as { detail?: string } | null)?.detail ??
        `${res.status} ${res.statusText}`,
    );
  }
  return (await res.json()) as QuoteFormResponse;
}

/** 외부 견적 추가 (PR-EXT) — 산출 X, 금액만. 갑지 row만 표시. */
export async function addSaleExternalQuote(
  saleId: string,
  body: { service: string; amount: number; vat_included?: boolean },
): Promise<QuoteFormResponse> {
  const res = await authFetch(`/api/sales/${saleId}/quotes/external`, {
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
  return (await res.json()) as QuoteFormResponse;
}

/** 외부 견적 service/amount 수정 (PR-EXT). 첨부 PDF 보존. */
export async function updateSaleExternalQuote(
  saleId: string,
  quoteId: string,
  body: { service: string; amount: number; vat_included?: boolean },
): Promise<QuoteFormResponse> {
  const res = await authFetch(
    `/api/sales/${saleId}/quotes/external/${quoteId}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      (detail as { detail?: string } | null)?.detail ??
        `${res.status} ${res.statusText}`,
    );
  }
  return (await res.json()) as QuoteFormResponse;
}

/** 외부 견적 PDF 첨부 (PR-EXT-2) — multipart upload → Drive [견적서]/{YYYY}년/.
 * form.attached_pdf_url/name/file_id 갱신. 갑지 표에 첨부 → 링크 노출. */
export async function attachExternalQuotePdf(
  saleId: string,
  quoteId: string,
  file: File,
): Promise<QuoteFormResponse> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await authFetch(
    `/api/sales/${saleId}/quotes/external/${quoteId}/attach-pdf`,
    { method: "POST", body: fd },
  );
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      (detail as { detail?: string } | null)?.detail ??
        `${res.status} ${res.statusText}`,
    );
  }
  return (await res.json()) as QuoteFormResponse;
}

/** 견적 문서번호 수동 수정. suffix/input/result 보존. */
export async function updateQuoteDocNumber(
  saleId: string,
  quoteId: string,
  docNumber: string,
): Promise<QuoteFormResponse> {
  const res = await authFetch(
    `/api/sales/${saleId}/quotes/${quoteId}/doc-number`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ doc_number: docNumber }),
    },
  );
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      (detail as { detail?: string } | null)?.detail ??
        `${res.status} ${res.statusText}`,
    );
  }
  return (await res.json()) as QuoteFormResponse;
}

/** 견적 삭제 (PR-M1). suffix 재할당 X — hole 보존. */
export async function deleteSaleQuote(
  saleId: string,
  quoteId: string,
): Promise<void> {
  const res = await authFetch(`/api/sales/${saleId}/quotes/${quoteId}`, {
    method: "DELETE",
  });
  if (!res.ok && res.status !== 204) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      (detail as { detail?: string } | null)?.detail ??
        `${res.status} ${res.statusText}`,
    );
  }
}

/** 통합 견적서 PDF 다운로드 — parent_lead_id로 묶인 자식들과 함께 1 PDF (PR-G1).
 * showTotal=false면 갑지에 견적가 + 합계 row 숨김. */
export async function downloadQuoteBundlePdf(
  parentSaleId: string,
  showTotal: boolean = true,
): Promise<void> {
  await downloadPdfBlob(
    `/api/sales/${parentSaleId}/quote-bundle.pdf?show_total=${showTotal ? "true" : "false"}`,
    "quote-bundle.pdf",
  );
}

/** 통합 견적서 PDF를 WORKS Drive에 자동 저장 (PR-G2). parent의 `통합견적서첨부`
 * 컬럼에 web url 저장. 단일 PDF (`견적서첨부`)는 그대로 보존. */
export async function saveQuoteBundlePdfToDrive(
  parentSaleId: string,
  showTotal: boolean = true,
): Promise<Sale> {
  const res = await authFetch(
    `/api/sales/${parentSaleId}/quote-bundle/save-pdf-to-drive?show_total=${showTotal ? "true" : "false"}`,
    { method: "POST" },
  );
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      (detail as { detail?: string } | null)?.detail ??
        `${res.status} ${res.statusText}`,
    );
  }
  return (await res.json()) as Sale;
}

// ── 주간 업무일지 (PR-W) ──

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
  const qs = new URLSearchParams({ week_start: range.weekStart });
  if (range.weekEnd) qs.set("week_end", range.weekEnd);
  if (range.lastWeekStart) qs.set("last_week_start", range.lastWeekStart);
  if (forceRefresh) qs.set("force_refresh", "true");
  return qs.toString();
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

// ── 사내 공지 / 교육 일정 / 휴일 (PR-W Phase 2.4) ── (Phase 4-A — lib/api/notices.ts로 이동)
export * from "./api/notices";

// ── admin sync 트리거 + 상태 (PR-AR) ──
export * from "./api/adminSync";
