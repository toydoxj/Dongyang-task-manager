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
  project_ids?: string[];
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

/** 수주영업 단계. 노션 '단계' select 옵션. */
export const BID_STAGES = [
  "견적준비",
  "입찰대기",
  "우선협상",
  "낙찰",
  "실주",
] as const;

export interface Sale {
  id: string;
  name: string;          // 견적서명
  kind: SalesKind;
  stage: string;
  category: string[];     // 업무내용 multi_select
  estimated_amount: number | null;  // 견적금액 KRW
  is_bid: boolean;
  client_id: string;      // 의뢰처 relation 첫번째
  gross_floor_area: number | null;
  floors_above: number | null;
  floors_below: number | null;
  building_count: number | null;
  note: string;
  submission_date: string | null;
  vat_inclusive: string;
  performance_design_amount: number | null;
  wind_tunnel_amount: number | null;
  parent_lead_id: string;
  converted_project_id: string;
  assignees: string[];
  created_time: string | null;
  last_edited_time: string | null;
  url: string | null;
  expected_revenue: number;  // 백엔드 computed_field — 견적금액 × 단계별 수주확률
}

export interface SaleListResponse {
  items: Sale[];
  count: number;
}

export interface SaleCreateRequest {
  name: string;
  kind?: string;
  stage?: string;
  category?: string[];
  estimated_amount?: number;
  is_bid?: boolean;
  client_id?: string;
  gross_floor_area?: number;
  floors_above?: number;
  floors_below?: number;
  building_count?: number;
  note?: string;
  submission_date?: string;
  vat_inclusive?: string;
  performance_design_amount?: number;
  wind_tunnel_amount?: number;
  parent_lead_id?: string;
  assignees?: string[];
}

export type SaleUpdateRequest = Partial<SaleCreateRequest>;
