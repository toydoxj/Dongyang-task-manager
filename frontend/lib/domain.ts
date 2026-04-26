// 노션 백엔드와 매칭되는 도메인 타입.

export interface Project {
  id: string;
  code: string;
  master_code: string;
  name: string;
  client_text: string;
  client_relation_ids: string[];
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
