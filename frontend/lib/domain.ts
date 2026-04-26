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
  project_id: string;
  status?: string;
  progress?: number;
  start_date?: string;
  end_date?: string;
  priority?: string;
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
  assignees?: string[];
  teams?: string[];
  note?: string;
}

export interface CashflowEntry {
  id: string;
  type: "income" | "expense";
  date: string | null;
  amount: number;
  category: string;
  project_ids: string[];
  note: string;
}

export interface CashflowResponse {
  items: CashflowEntry[];
  income_total: number;
  expense_total: number;
  net: number;
  count: number;
}

export const PROJECT_STAGES = [
  "진행중",
  "대기",
  "보류",
  "완료",
  "타절",
  "종결",
  "이관",
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
