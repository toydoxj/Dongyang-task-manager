// 노션 백엔드와 매칭되는 도메인 타입.

export interface Project {
  id: string;
  code: string;
  master_code: string;
  master_project_id: string;
  master_project_name: string;
  name: string;
  client_text: string;
  client_relation_ids: string[];
  client_names: string[];
  stage: string; // 진행중|대기|보류|완료|타절|종결|이관
  contract_signed: boolean;
  completed: boolean;
  start_date: string | null;
  contract_start: string | null;
  contract_end: string | null;
  end_date: string | null;
  assignees: string[];
  teams: string[];
  work_types: string[];
  contract_amount: number | null;
  vat: number | null;
  method_review_fee: number | null;
  progress_payment: number | null;
  outsourcing_estimated: number | null;
  collection_rate: unknown;
  collection_total: number | null;
  expense_total: number | null;
  last_edited_time: string | null;
  url: string | null;
  drive_url: string;
}

export interface ProjectListResponse {
  items: Project[];
  count: number;
}

export interface ProjectCreateRequest {
  name: string;
  code?: string;
  client_text?: string;
  client_relation_ids?: string[];
  stage?: string;
  teams?: string[];
  assignees?: string[];
  work_types?: string[];
  start_date?: string;
  contract_start?: string;
  contract_end?: string;
  contract_amount?: number;
  vat?: number;
}

export interface ProjectUpdateRequest {
  name?: string;
  code?: string;
  client_text?: string;
  client_relation_ids?: string[];
  stage?: string;
  teams?: string[];
  assignees?: string[];
  work_types?: string[];
  start_date?: string;
  contract_start?: string;
  contract_end?: string;
  end_date?: string;
  contract_amount?: number;
  vat?: number;
}

export type DriveFileType =
  | "FOLDER"
  | "DOC"
  | "IMAGE"
  | "VIDEO"
  | "AUDIO"
  | "ZIP"
  | "EXE"
  | "ETC";

export interface DriveItem {
  fileId: string;
  fileName: string;
  fileType: DriveFileType;
  fileSize: number;
  modifiedTime: string;
  webUrl: string;
}

export interface DriveChildrenResponse {
  items: DriveItem[];
  next_cursor: string;
}

export interface DriveUploadResultItem {
  fileName: string;
  fileId: string;
  fileSize: number;
  fileType: DriveFileType;
  webUrl: string;
  error: string; // 실패 시 메시지, 성공이면 빈 문자열
}

export interface DriveUploadResponse {
  items: DriveUploadResultItem[];
}

export interface Client {
  id: string;
  name: string;
  category: string;
}

export interface SubProjectRef {
  id: string;
  name: string;
  code: string;
  stage: string;
}

export interface MasterProject {
  id: string;
  name: string;
  code: string;
  address: string;
  usage: string[];
  structure: string[];
  floors_above: number | null;
  floors_below: number | null;
  height: number | null;
  area: number | null;
  units: number | null;
  high_rise: boolean;
  multi_use: boolean;
  special_structure: boolean;
  completed: boolean;
  special_types: string[];
  sub_project_ids: string[];
  sub_projects: SubProjectRef[];
  url: string | null;
}

export interface MasterProjectUpdate {
  name?: string;
  code?: string;
  address?: string;
  usage?: string[];
  structure?: string[];
  floors_above?: number | null;
  floors_below?: number | null;
  height?: number | null;
  area?: number | null;
  units?: number | null;
  high_rise?: boolean;
  multi_use?: boolean;
  special_structure?: boolean;
  completed?: boolean;
  special_types?: string[];
}

export interface MasterImage {
  block_id: string;
  url: string;
  caption: string;
  source: string;
}

export interface MasterImageList {
  items: MasterImage[];
}

export interface MasterOptions {
  usage: string[];
  structure: string[];
  special_types: string[];
}

export interface ProjectOptions {
  work_types: string[];
}

// ── 직원 ──

export interface Employee {
  id: number;
  name: string;
  sort_order: number;
  position: string;
  team: string;
  degree: string;
  license: string;
  grade: string;
  email: string;
  linked_user_id: number | null;
  resigned_at: string | null; // ISO YYYY-MM-DD
}

export interface EmployeeListResponse {
  items: Employee[];
  count: number;
}

export interface EmployeeUpdate {
  name?: string;
  position?: string;
  team?: string;
  degree?: string;
  license?: string;
  grade?: string;
  email?: string;
  resigned_at?: string | null;
}

export type EmployeeView = "active" | "resigned" | "all";

export interface EmployeeCreate {
  name: string;
  position?: string;
  team?: string;
  degree?: string;
  license?: string;
  grade?: string;
  email?: string;
}

export interface EmployeeImportResult {
  inserted: number;
  updated: number;
  skipped: number;
  total_rows: number;
}

export interface ClientListResponse {
  items: Client[];
  count: number;
}

export const WORK_TYPES = [
  "구조설계",
  "현장기술지원",
  "안전진단(부분)",
  "구조검토",
  "구조감리",
  "내진보강설계",
  "내진성능평가",
  "내진기술감리",
  "비구조내진",
  "정밀안전점검",
  "정밀안전진단",
  "기술제안",
  "VE설계",
  "증축설계",
  "해체계획",
  "해체감리",
  "구조계획",
  "기타",
] as const;

export interface Task {
  id: string;
  title: string;
  code: string;
  project_ids: string[];
  sales_ids: string[];        // 분류='영업(서비스)'일 때 영업 row page_id
  status: string; // 시작 전|진행 중|완료|보류
  progress: number | null; // 0~1
  start_date: string | null;
  end_date: string | null;
  actual_end_date: string | null;
  priority: string; // 높음|보통|낮음
  difficulty: string; // 매우높음|높음|중간|낮음|매우낮음
  category: string;   // 프로젝트|개인업무|사내잡무|교육|서비스|외근|출장|휴가
  activity: string;   // 사무실|외근|출장 (분류와 독립)
  assignees: string[];
  teams: string[];
  note: string;
  weekly_plan_text: string;  // PR-W Phase 2.2 — 금주예정사항
  created_time: string | null;
  last_edited_time: string | null;
  url: string | null;
}

export interface TaskListResponse {
  items: Task[];
  count: number;
}

export interface TaskCreateRequest {
  title: string;
  project_id?: string;  // 분류='프로젝트'일 때만 필수
  sale_id?: string;     // 분류='영업(서비스)'일 때만 필수
  category?: string;    // 분류
  activity?: string;    // 활동 (사무실/외근/출장)
  status?: string;
  progress?: number;
  start_date?: string;
  end_date?: string;
  priority?: string;
  difficulty?: string;
  assignees?: string[];
  teams?: string[];
  note?: string;
  code?: string;
}

export interface TaskUpdateRequest {
  title?: string;
  status?: string;
  progress?: number;
  start_date?: string;
  end_date?: string;
  actual_end_date?: string;
  priority?: string;
  difficulty?: string;
  category?: string;
  activity?: string;
  assignees?: string[];
  teams?: string[];
  note?: string;
  weekly_plan_text?: string;  // PR-W Phase 2.2 — 금주예정사항
  project_ids?: string[];
  sales_ids?: string[];
}

export interface ContractItem {
  id: string;
  project_id: string;
  client_id: string;
  client_name?: string;
  label: string;
  amount: number;
  vat: number;
  sort_order: number;
}

export interface ContractItemListResponse {
  items: ContractItem[];
  count: number;
}

export interface CashflowEntry {
  id: string;
  type: "income" | "expense";
  date: string | null;
  amount: number;
  category: string;
  project_ids: string[];
  note: string;
  // income 전용 — 노션 '실지급' relation (발주처 DB와 동일)
  round_no?: number | null;
  payer_relation_ids?: string[];
  payer_names?: string[];
  // 분담 항목 매칭 (공동수급/추가용역). 없으면 legacy 단일 모드.
  contract_item_id?: string | null;
  contract_item_label?: string | null;
}

export interface CashflowResponse {
  items: CashflowEntry[];
  income_total: number;
  expense_total: number;
  net: number;
  count: number;
}

// '이관'은 운영 정책상 제외 — backend는 여전히 받지만 UI dropdown에는 미노출
export const PROJECT_STAGES = [
  "진행중",
  "대기",
  "보류",
  "완료",
  "타절",
  "종결",
] as const;

export const TEAMS = [
  "구조1팀",
  "구조2팀",
  "구조3팀",
  "구조4팀",
  "진단팀",
  "기타",
] as const;

export const TASK_STATUSES = ["시작 전", "진행 중", "완료", "보류"] as const;
export const TASK_PRIORITIES = ["높음", "보통", "낮음"] as const;
export const TASK_DIFFICULTIES = [
  "매우높음",
  "높음",
  "중간",
  "낮음",
  "매우낮음",
] as const;

// 새 분류 체계 — 외근/출장은 활동(activity)으로만, 휴가는 휴가(연차) 1개로 통합
export const TASK_CATEGORIES = [
  "프로젝트",
  "영업(서비스)",
  "개인업무",
  "사내잡무",
  "교육",
  "휴가(연차)",
] as const;
export type TaskCategory = (typeof TASK_CATEGORIES)[number];

/** 시간(시:분)까지 지정해야 하는 일정 분류.
 * 휴가는 반차/시간 단위 등 시간 지정이 필요. "휴가"는 옛 표기 호환. */
export const TIME_BASED_CATEGORIES: readonly string[] = ["휴가(연차)", "휴가"];

/** 활동 유형 — 분류와 독립. 프로젝트 task의 외근/출장 표시용. */
export const ACTIVITY_TYPES = ["사무실", "외근", "출장"] as const;
export type ActivityType = (typeof ACTIVITY_TYPES)[number];

/** 시간 지정이 필요한 활동 (외근/출장). */
export const TIME_BASED_ACTIVITIES: readonly string[] = ["외근", "출장"];

/** task가 시간 기반 일정인지 판정 — 분류 또는 활동 중 하나라도 시간 기반이면. */
export function isTimeBasedTask(category?: string, activity?: string): boolean {
  return (
    (category != null && TIME_BASED_CATEGORIES.includes(category)) ||
    (activity != null && TIME_BASED_ACTIVITIES.includes(activity))
  );
}

/** /me 일정 카드에 표시되어야 할 task인지 — 분류=외근/출장/휴가/휴가(연차) OR 활동=외근/출장 */
export function isScheduleTask(category?: string, activity?: string): boolean {
  return (
    (category != null && SCHEDULE_CATEGORIES.includes(category as never)) ||
    (activity != null && TIME_BASED_ACTIVITIES.includes(activity))
  );
}

/** 일정 카드(외근/출장/휴가)에 표시할 분류. 옛 표기와 새 표기 모두 호환. */
export const SCHEDULE_CATEGORIES = ["외근", "출장", "휴가", "휴가(연차)"] as const;

/** 기타 업무(프로젝트도 일정도 아닌)에 묶을 분류.
 * '서비스' 는 옛 표기 (새 옵션은 '영업(서비스)'). 데이터 호환 위해 둘 다 포함. */
export const NON_PROJECT_WORK_CATEGORIES = [
  "개인업무",
  "사내잡무",
  "교육",
  "서비스",
  "영업(서비스)",
] as const;

// ── 영업(Sales) ──

/** 영업 유형. 노션 '유형' select 옵션과 일치. */
export type SalesKind = "수주영업" | "기술지원" | "";

/** 수주영업 단계. 노션 '단계' select 옵션. 사장 결정 5단계. */
export const BID_STAGES = [
  "준비",
  "진행",
  "제출",
  "완료",
  "종결",
] as const;

/** /convert 가능한 단계 — 백엔드 CONVERTIBLE_STAGES와 일치. */
export const CONVERTIBLE_STAGES: readonly string[] = ["완료"];

export interface Sale {
  id: string;
  code: string;          // 영업코드 {YY}-영업-{NNN} (자동 부여, 노션 수정 가능)
  name: string;          // 견적서명
  kind: SalesKind;
  stage: string;
  category: string[];     // 업무내용 multi_select
  estimated_amount: number | null;  // 견적금액 KRW
  probability: number | null;        // 수주확률 0~100 (PM 직접 입력)
  is_bid: boolean;
  client_id: string;      // 의뢰처 relation 첫번째
  quote_doc_number: string;  // 견적서 문서번호 {YY}-{CC}-{NNN}
  quote_form_data: { input?: QuoteInput; result?: QuoteResult } | Record<string, never>;
  /** 견적서 종류 (PR-Q1) — 빈 값이면 '구조설계' fallback */
  quote_type: string;
  gross_floor_area: number | null;
  floors_above: number | null;
  floors_below: number | null;
  building_count: number | null;
  note: string;
  submission_date: string | null;
  vat_inclusive: string;
  performance_design_amount: number | null;
  wind_tunnel_amount: number | null;
  converted_project_id: string;
  /** 영업 위치 — 영업 row 단위. 견적서 탭에서 echo. */
  location: string;
  assignees: string[];
  created_time: string | null;
  last_edited_time: string | null;
  url: string | null;
  expected_revenue: number;  // 백엔드 computed_field — 견적금액 × 수주확률/100
}

export interface SaleListResponse {
  items: Sale[];
  count: number;
}

export interface SaleCreateRequest {
  name: string;
  code?: string;  // 빈 값/미지정이면 backend가 {YY}-영업-{NNN} 자동 부여
  kind?: string;
  stage?: string;
  category?: string[];
  estimated_amount?: number;
  probability?: number;
  is_bid?: boolean;
  client_id?: string;
  // 견적서 작성 툴 (PR5)
  quote_doc_number?: string;  // 빈 값/미지정이면 자동 부여 ({YY}-{CC}-{NNN})
  quote_form_data?: { input: QuoteInput; result: QuoteResult };
  /** 견적서 종류 (PR-Q1) — 빈 값이면 '구조설계' fallback */
  quote_type?: string;
  gross_floor_area?: number;
  floors_above?: number;
  floors_below?: number;
  building_count?: number;
  note?: string;
  submission_date?: string;
  vat_inclusive?: string;
  performance_design_amount?: number;
  wind_tunnel_amount?: number;
  /** 영업 위치. */
  location?: string;
  assignees?: string[];
}

export type SaleUpdateRequest = Partial<SaleCreateRequest>;

// ── 견적서 작성 툴 (PR5) ──

/** 직접경비 동적 항목. */
export interface DirectExpenseItem {
  name: string;
  amount: number;
}

/** 용역범위 list 항목 — 라벨(포함/제외/일반) + 텍스트. PDF에 [포함]/[제외] 태그 표시. */
export type SpecialNoteType = "include" | "exclude" | "plain";
export interface SpecialNoteItem {
  type: SpecialNoteType;
  text: string;
}

/** 견적서 종류 — 백엔드 QuoteType enum과 일치 (값=한글 라벨, 노션 select name). */
/** 한국엔지니어링협회 통계법 기반 기술자 등급 (건설분야 단가 적용).
 * 매년 1월 단가 표 갱신 시 backend ENGINEERING_RATES_BY_GRADE도 동기 업데이트. */
export const ENGINEER_GRADES = [
  "기술사",
  "특급기술자",
  "고급기술자",
  "중급기술자",
  "초급기술자",
  "고급숙련기술자",
  "중급숙련기술자",
  "초급숙련기술자",
] as const;
export type EngineerGrade = (typeof ENGINEER_GRADES)[number];

export const QUOTE_TYPES = [
  "구조설계",
  "구조검토",
  "성능기반내진설계",
  "정기안전점검",
  "정밀점검",
  "정밀안전진단",
  "건축물관리법점검",
  "내진성능평가",
  "내진보강설계",
  "3자검토",
  "구조감리",
  "현장기술지원",
  "기타",
] as const;
export type QuoteType = (typeof QUOTE_TYPES)[number];

/** 견적서 입력값 — 백엔드 QuoteInput과 1:1 대응. */
export interface QuoteInput {
  /** 견적서 종류 — 빈 값/미지정이면 '구조설계' fallback */
  quote_type?: QuoteType;
  /** quote_type='기타'일 때만 PDF 헤더 제목으로 사용 */
  custom_title?: string;
  service_name?: string;
  location?: string;
  structure_form?: string;
  /** 영업 정보와 동기화 (default true) — true면 영업정보 탭에서 echo (견적 form
   * input disabled). false면 견적별 자체 입력 (영업정보 변경 영향 X). 한 영업에
   * 종류·대상 건축물이 다른 견적이 섞여 있는 케이스 대응. */
  sync_with_sale?: boolean;
  /** 지상층수 — 영업 정보 Sale.floors_above와 동일 필드 */
  floors_above?: number | null;
  /** 지하층수 — 영업 정보 Sale.floors_below와 동일 필드 */
  floors_below?: number | null;
  /** 동수 — 영업 정보 Sale.building_count와 동일 필드 */
  building_count?: number | null;
  /** legacy 자유 텍스트 — 비면 above/below로 자동 표기 */
  floors_text?: string;
  recipient_company?: string;
  recipient_person?: string;
  recipient_phone?: string;
  recipient_email?: string;
  gross_floor_area?: number;
  type_rate?: number;
  structure_rate?: number;
  coefficient?: number;
  /** null/undefined: 자동 산출. 값이 있으면 그 값 사용. 정기/정밀점검은 시특법 4계수
   * 곱한 소수 인.일(15.24, 36.19 등) 입력이 필요해 float 허용. */
  manhours_override?: number | null;
  /** 직접인건비 단가 등급. null이면 종류별 default (구조감리=기술사, 3자검토=특급,
   * 그 외=고급기술자). EngineerGrade 8종 중 선택. */
  engineer_grade?: EngineerGrade | null;
  /** BMA 책임자/점검자 등급. null이면 default(책임자=특급, 점검자=초급). */
  bma_responsible_grade?: EngineerGrade | null;
  bma_inspector_grade?: EngineerGrade | null;
  /** 건축물관리법점검 (PR-Q4) — 책임자/점검자 인.일 분리 입력 (수동 fallback). */
  inspection_responsible_days?: number | null;
  inspection_inspector_days?: number | null;
  /** 건축물관리법점검 자동 산정 (PR-Q4b) — 산정표 기반.
   * "정기" | "정기+구조" 입력 + gross_floor_area + building_usage 채우면 자동.
   * 빈 값이면 inspection_responsible_days/inspector_days 수동 흐름 fallback. */
  bma_inspection_type?: string;
  /** 제38조② 구조안전 생략 (× 0.8) */
  bma_skip_structural?: boolean;
  /** 제38조③ 급수·배수·냉난방·환기 생략 (× 0.9) */
  bma_skip_utility?: boolean;
  /** 제39조 선택과업비 (마감재 해체·복구) — 자유 입력 */
  bma_optional_task_amount?: number;
  /** 내진성능평가 (PR-Q8) — ① 현장조사 외업/내업, ② 해석 인.일 (3 필드 분리).
   * has_structural_drawings + gross_floor_area 있으면 PR-Q8b 보간 자동 채움. */
  field_outdoor_days?: number | null;
  field_indoor_days?: number | null;
  analysis_days?: number | null;
  /** 내진성능평가 보간용 — 구조도면 보유 여부 (xlsx F44). null=수동 입력 모드. */
  has_structural_drawings?: boolean | null;
  /** 동적 직접경비 항목 (이름 + 금액). 비어있으면 legacy 합산 fallback. */
  direct_expense_items?: DirectExpenseItem[];
  overhead_pct?: number;
  tech_fee_pct?: number;
  adjustment_pct?: number;
  /** 절삭 단위 — 1_000_000(백만) / 100_000(십만) / 10_000(만) / 0(절삭 없음). default 1_000_000 */
  truncate_unit?: number;
  /** 최종 금액 직접 지정 — 정수면 truncate_unit 무시. */
  final_override?: number | null;
  vat_included?: boolean;
  payment_terms?: string;
  /** 용역범위 list (신) — 항목별 라벨(포함/제외/일반) + 텍스트. */
  special_notes_items?: SpecialNoteItem[];
  /** 용역범위 legacy — textarea 라인별 [포함]/[제외] 끝맺음 (backward 호환). */
  special_notes?: string;
  /** 견적 비고 — 자유 입력. */
  quote_note?: string;
  // ── 시특법 점검 자동 산정 (PR-Q5b) — 정기/정밀점검/정밀안전진단 ──
  // structure_form은 위 메타 필드를 그대로 사용 (별표 23(1) 키).
  /** 별표 23(2) 용도: 업무용/상업용/주거용/특수용/경기장 등 */
  building_usage?: string;
  /** 준공년도 — 입력 시 backend가 산정 시점 - completion_year로 경과년수 자동 계산 */
  completion_year?: number | null;
  /** 경과년수 (제62조 2호) — completion_year 미입력 시 fallback */
  aging_years?: number | null;
  /** 구조복잡도 (제62조 1호): 단순/보통/복잡 */
  complexity?: string;
  /** 전차보고서 (제62조 3호): 미제공/CAD/보고서+CAD */
  prev_report?: string;
  /** 시설물 형태 (제61조): 기본/인접/군집(소)/군집(대)/혼합 */
  facility_type?: string;
  /** 인접·군집 부속 면적 list */
  sub_facility_areas?: number[];
  /** 직접경비 단가 (사용자 입력, 시특법 자동 산정용) */
  travel_unit_cost?: number;
  helper_daily_wage?: number;
  vehicle_daily_cost?: number;
  fuel_unit_price?: number;
  print_unit_cost?: number;
  print_copies?: number;
  risk_pct?: number;
  machine_pct?: number;
  // ── 별표 26 선택과업 ──
  /** A. 실측도면 작성 */
  opt_field_drawings?: boolean;
  /** "기본"(10%) | "상세"(20%) */
  opt_field_drawings_scope?: string;
  /** B. 구조해석 */
  opt_structural_analysis?: boolean;
  /** "RC계" | "PC조" | "특수구조" */
  opt_analysis_struct_type?: string;
  /** 구조해석 개소 수 */
  opt_analysis_count?: number;
  /** C. 내진성 평가 */
  opt_seismic_eval?: boolean;
  /** 2.0(간략) ~ 3.0(정밀) */
  opt_seismic_multiplier?: number;
  /** 그 외 자유 입력 (별표 26-6/7/11/12/13/16) */
  opt_other_items?: DirectExpenseItem[];
  // ── legacy (기존 영업 호환, 신규는 direct_expense_items 사용) ──
  printing_fee?: number;
  survey_fee?: number;
  transport_persons?: number;
}

/** 영업 1건 안 단일 견적 form (PR-M0~M2). 영업당 N개 가능 — 각자 doc_number와
 * suffix(영업 내 인덱스 영문, A/B/C/...). full_doc은 표시 형식 "26-04-001A".
 * is_external이면 외부 견적 (PR-EXT) — 산출 X, 갑지 row만 (선택 PDF 첨부 PR-EXT-2). */
export interface QuoteFormResponse {
  id: string;
  doc_number: string;
  suffix: string;
  full_doc: string;
  input: QuoteInput;
  result: QuoteResult;
  is_external?: boolean;
  service?: string;
  amount?: number;
  /** 외부 견적 VAT 포함 여부 — default false (VAT 별도). 갑지 금액 옆 라벨. */
  vat_included?: boolean;
  attached_pdf_url?: string;
  attached_pdf_name?: string;
  attached_pdf_file_id?: string;
}

/** 별표 26 추가과업 항목별 분해 — PDF·산정 패널 표시용. */
export interface OptionalTaskBreakdown {
  label: string;
  persons: number;
  unit_rate: number;
  base_pct: number;
  base_amount: number;
  amount: number;
  note: string;
}

/** 기본과업 인.일 산식 단계별 — 별표 22 base → 별표 23 보정 → 제62조 → 추가과업 합산. */
export interface ManhourFormulaStep {
  label: string;
  operator: string;
  value: number;
  note: string;
}

/** 견적서 산출 결과 — 백엔드 QuoteResult. */
export interface QuoteResult {
  manhours_baseline: number;
  manhours_baseline_rounded: number;
  manhours_total: number;
  direct_labor: number;
  direct_expense: number;
  overhead: number;
  tech_fee: number;
  subtotal: number;
  adjusted: number;
  truncated: number;
  final: number;
  vat_amount: number;
  final_with_vat: number;
  per_pyeong_area: number;
  per_pyeong: number;
  /** 별표 25 직접경비 항목별 분해 — 시특법 자동 산정 시에만 채워짐. */
  direct_expense_breakdown?: OptionalTaskBreakdown[];
  /** 별표 26 추가과업 분해 — 시특법 자동 산정 시에만 채워짐. */
  optional_tasks?: OptionalTaskBreakdown[];
  /** 기본과업 인.일 산식 단계별 — 시특법 자동 산정 시 PDF 표시용. */
  manhours_formula?: ManhourFormulaStep[];
  /** 시특법 자동 산정 외업/내업 인.일. 0이면 미적용. */
  manhours_outdoor?: number;
  manhours_indoor?: number;
}
