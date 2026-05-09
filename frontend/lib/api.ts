// 백엔드 호출 헬퍼 — 인증 토큰 자동 주입 + JSON 파싱 + 에러 메시지 통일.

import { authFetch } from "./auth";
import { API_BASE } from "./types";
import type {
  CashflowEntry,
  CashflowResponse,
  Client,
  ClientListResponse,
  ContractItem,
  ContractItemListResponse,
  DriveChildrenResponse,
  DriveUploadResponse,
  Employee,
  EmployeeCreate,
  EmployeeImportResult,
  EmployeeListResponse,
  EmployeeUpdate,
  EmployeeView,
  MasterImage,
  MasterImageList,
  MasterOptions,
  MasterProject,
  MasterProjectUpdate,
  Project,
  ProjectCreateRequest,
  ProjectListResponse,
  ProjectOptions,
  QuoteFormResponse,
  QuoteInput,
  QuoteResult,
  Sale,
  SaleCreateRequest,
  SaleListResponse,
  SaleUpdateRequest,
  Task,
  TaskCreateRequest,
  TaskListResponse,
  TaskUpdateRequest,
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

// ── 프로젝트 ──

export async function listProjects(filters: {
  assignee?: string;
  stage?: string;
  team?: string;
  completed?: boolean;
  mine?: boolean;
} = {}): Promise<ProjectListResponse> {
  const res = await authFetch(`/api/projects${qs(filters)}`);
  return jsonOrThrow<ProjectListResponse>(res);
}

export async function getProject(pageId: string): Promise<Project> {
  const res = await authFetch(`/api/projects/${pageId}`);
  return jsonOrThrow<Project>(res);
}

export async function assignMe(
  pageId: string,
  options: { setToWaiting?: boolean; forUser?: string } = {},
): Promise<Project> {
  const res = await authFetch(
    `/api/projects/${pageId}/assign${qs({
      set_to_waiting: options.setToWaiting,
      for_user: options.forUser,
    })}`,
    { method: "POST" },
  );
  return jsonOrThrow<Project>(res);
}

export async function unassignMe(
  pageId: string,
  options: { forUser?: string } = {},
): Promise<Project> {
  const res = await authFetch(
    `/api/projects/${pageId}/assign${qs({ for_user: options.forUser })}`,
    { method: "DELETE" },
  );
  return jsonOrThrow<Project>(res);
}

export async function updateProject(
  pageId: string,
  body: import("@/lib/domain").ProjectUpdateRequest,
): Promise<Project> {
  const res = await authFetch(`/api/projects/${pageId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<Project>(res);
}

export async function createProject(
  body: ProjectCreateRequest,
  options: { forUser?: string } = {},
): Promise<Project> {
  const res = await authFetch(
    `/api/projects${qs({ for_user: options.forUser })}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  return jsonOrThrow<Project>(res);
}

export async function getProjectOptions(): Promise<ProjectOptions> {
  const res = await authFetch(`/api/projects/options`);
  return jsonOrThrow<ProjectOptions>(res);
}

export async function syncProjectStage(pageId: string): Promise<Project> {
  const res = await authFetch(`/api/projects/${pageId}/sync-stage`, {
    method: "POST",
  });
  return jsonOrThrow<Project>(res);
}

export interface ProjectLogEntry {
  id: string;
  event_at: string;
  title: string;
  action: string;
  target: string;
  actor: string;
}

export interface ProjectLogResponse {
  items: ProjectLogEntry[];
  count: number;
}

export async function getProjectLog(
  pageId: string,
): Promise<ProjectLogResponse> {
  const res = await authFetch(`/api/projects/${pageId}/log`);
  return jsonOrThrow<ProjectLogResponse>(res);
}

export async function setProjectStage(
  pageId: string,
  stage: string,
): Promise<Project> {
  const res = await authFetch(
    `/api/projects/${pageId}/stage${qs({ stage })}`,
    { method: "PATCH" },
  );
  return jsonOrThrow<Project>(res);
}

// ── 업무TASK ──

export async function listTasks(filters: {
  project_id?: string;
  assignee?: string;
  status?: string;
  mine?: boolean;
  schedule_only?: boolean;
} = {}): Promise<TaskListResponse> {
  const res = await authFetch(`/api/tasks${qs(filters)}`);
  return jsonOrThrow<TaskListResponse>(res);
}

export async function createTask(body: TaskCreateRequest): Promise<Task> {
  const res = await authFetch(`/api/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<Task>(res);
}

export async function updateTask(
  pageId: string,
  body: TaskUpdateRequest,
): Promise<Task> {
  const res = await authFetch(`/api/tasks/${pageId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<Task>(res);
}

export async function archiveTask(pageId: string): Promise<{ status: string }> {
  const res = await authFetch(`/api/tasks/${pageId}`, { method: "DELETE" });
  return jsonOrThrow<{ status: string }>(res);
}

// ── Cashflow ──

export async function getCashflow(filters: {
  project_id?: string;
  date_from?: string;
  date_to?: string;
  flow?: "income" | "expense" | "all";
} = {}): Promise<CashflowResponse> {
  const res = await authFetch(`/api/cashflow${qs(filters)}`);
  return jsonOrThrow<CashflowResponse>(res);
}

// ── 수금 CRUD (admin) ──

export interface IncomeCreateRequest {
  date: string;
  amount: number;
  round_no?: number | null;
  project_ids?: string[];
  payer_relation_ids?: string[];
  contract_item_id?: string | null;
  note?: string;
}

export interface IncomeUpdateRequest {
  date?: string | null;
  amount?: number | null;
  round_no?: number | null;
  project_ids?: string[] | null;
  payer_relation_ids?: string[] | null;
  contract_item_id?: string | null;
  note?: string | null;
}

export async function createIncome(
  body: IncomeCreateRequest,
): Promise<CashflowEntry> {
  const res = await authFetch(`/api/cashflow/incomes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<CashflowEntry>(res);
}

export async function updateIncome(
  pageId: string,
  body: IncomeUpdateRequest,
): Promise<CashflowEntry> {
  const res = await authFetch(`/api/cashflow/incomes/${pageId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<CashflowEntry>(res);
}

export async function deleteIncome(pageId: string): Promise<void> {
  const res = await authFetch(`/api/cashflow/incomes/${pageId}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `삭제 실패 (${res.status})`);
  }
}

// ── 협력업체(발주처) ──

export async function listClients(): Promise<ClientListResponse> {
  const res = await authFetch(`/api/clients`);
  return jsonOrThrow<ClientListResponse>(res);
}

export interface ClientCreateRequest {
  name: string;
  category?: string;
}

export async function createClient(
  body: ClientCreateRequest,
): Promise<Client> {
  const res = await authFetch(`/api/clients`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<Client>(res);
}

export interface ClientUpdateRequest {
  name?: string | null;
  category?: string | null;
}

export async function updateClient(
  pageId: string,
  body: ClientUpdateRequest,
): Promise<Client> {
  const res = await authFetch(`/api/clients/${pageId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<Client>(res);
}

export async function deleteClient(pageId: string): Promise<void> {
  const res = await authFetch(`/api/clients/${pageId}`, { method: "DELETE" });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `삭제 실패 (${res.status})`);
  }
}

// ── 계약 항목 (공동수급/추가용역) ──

export interface ContractItemCreateRequest {
  project_id: string;
  client_id: string;
  label?: string;
  amount?: number;
  vat?: number;
  sort_order?: number;
}

export interface ContractItemUpdateRequest {
  project_id?: string | null;
  client_id?: string | null;
  label?: string | null;
  amount?: number | null;
  vat?: number | null;
  sort_order?: number | null;
}

export async function listContractItems(
  projectId?: string,
): Promise<ContractItemListResponse> {
  const path = projectId
    ? `/api/contract-items?project_id=${encodeURIComponent(projectId)}`
    : `/api/contract-items`;
  const res = await authFetch(path);
  return jsonOrThrow<ContractItemListResponse>(res);
}

export async function createContractItem(
  body: ContractItemCreateRequest,
): Promise<ContractItem> {
  const res = await authFetch(`/api/contract-items`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<ContractItem>(res);
}

export async function updateContractItem(
  pageId: string,
  body: ContractItemUpdateRequest,
): Promise<ContractItem> {
  const res = await authFetch(`/api/contract-items/${pageId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<ContractItem>(res);
}

export async function deleteContractItem(pageId: string): Promise<void> {
  const res = await authFetch(`/api/contract-items/${pageId}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `삭제 실패 (${res.status})`);
  }
}

// ── 마스터 프로젝트 ──

export async function getMasterProject(pageId: string): Promise<MasterProject> {
  const res = await authFetch(`/api/master-projects/${pageId}`);
  return jsonOrThrow<MasterProject>(res);
}

export async function getMasterOptions(): Promise<MasterOptions> {
  const res = await authFetch(`/api/master-projects/options`);
  return jsonOrThrow<MasterOptions>(res);
}

export async function updateMasterProject(
  pageId: string,
  body: MasterProjectUpdate,
): Promise<MasterProject> {
  const res = await authFetch(`/api/master-projects/${pageId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<MasterProject>(res);
}

export async function listMasterImages(
  pageId: string,
): Promise<MasterImageList> {
  const res = await authFetch(`/api/master-projects/${pageId}/images`);
  return jsonOrThrow<MasterImageList>(res);
}

export async function uploadMasterImage(
  pageId: string,
  file: File,
  caption: string = "",
): Promise<MasterImage> {
  const fd = new FormData();
  fd.append("file", file, file.name);
  if (caption) fd.append("caption", caption);
  // Content-Type은 FormData가 자동 설정 (boundary 포함). authFetch가 덮어쓰지 않도록 헤더 미지정.
  const res = await authFetch(`/api/master-projects/${pageId}/images`, {
    method: "POST",
    body: fd,
  });
  return jsonOrThrow<MasterImage>(res);
}

// ── 사용자 관리 (admin) ──

import type { UserInfo, UserRole } from "./types";

export async function listUsers(): Promise<UserInfo[]> {
  const res = await authFetch(`/api/auth/users`);
  return jsonOrThrow<UserInfo[]>(res);
}

export async function approveUser(id: number): Promise<UserInfo> {
  const res = await authFetch(`/api/auth/users/${id}/approve`, {
    method: "POST",
  });
  return jsonOrThrow<UserInfo>(res);
}

export async function rejectUser(id: number): Promise<{ status: string }> {
  const res = await authFetch(`/api/auth/users/${id}/reject`, {
    method: "POST",
  });
  return jsonOrThrow<{ status: string }>(res);
}

export async function setUserRole(id: number, role: UserRole): Promise<UserInfo> {
  const res = await authFetch(`/api/auth/users/${id}/role`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role }),
  });
  return jsonOrThrow<UserInfo>(res);
}

export interface AdminUserPatch {
  name?: string;
  email?: string;
  notion_user_id?: string;
}

export async function updateUserAsAdmin(
  id: number,
  patch: AdminUserPatch,
): Promise<UserInfo> {
  const res = await authFetch(`/api/auth/users/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  return jsonOrThrow<UserInfo>(res);
}

export async function deleteUser(id: number): Promise<void> {
  const res = await authFetch(`/api/auth/users/${id}`, { method: "DELETE" });
  if (!res.ok) {
    const detail = await res
      .json()
      .then((d) => (d as { detail?: string }).detail)
      .catch(() => undefined);
    throw new Error(detail ?? `${res.status} ${res.statusText}`);
  }
}

// ── 직원 (admin) ──

/** 이름 → 팀 매핑 (재직중 직원만, 모든 사용자 호출 가능). */
export async function getEmployeeTeamsMap(): Promise<Record<string, string>> {
  const res = await authFetch(`/api/admin/employees/teams-map`);
  return jsonOrThrow<Record<string, string>>(res);
}

export async function listEmployees(
  q?: string,
  view: EmployeeView = "active",
): Promise<EmployeeListResponse> {
  const res = await authFetch(`/api/admin/employees${qs({ q, view })}`);
  return jsonOrThrow<EmployeeListResponse>(res);
}

export async function resignEmployee(
  id: number,
  on?: string,
): Promise<Employee> {
  const res = await authFetch(
    `/api/admin/employees/${id}/resign${qs({ on })}`,
    { method: "POST" },
  );
  return jsonOrThrow<Employee>(res);
}

export async function restoreEmployee(id: number): Promise<Employee> {
  const res = await authFetch(`/api/admin/employees/${id}/restore`, {
    method: "POST",
  });
  return jsonOrThrow<Employee>(res);
}

export async function createEmployee(body: EmployeeCreate): Promise<Employee> {
  const res = await authFetch(`/api/admin/employees`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<Employee>(res);
}

export async function updateEmployee(
  id: number,
  body: EmployeeUpdate,
): Promise<Employee> {
  const res = await authFetch(`/api/admin/employees/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<Employee>(res);
}

export async function deleteEmployee(id: number): Promise<void> {
  const res = await authFetch(`/api/admin/employees/${id}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const detail = await res
      .json()
      .then((d) => (d as { detail?: string }).detail)
      .catch(() => undefined);
    throw new Error(detail ?? `${res.status} ${res.statusText}`);
  }
}

export async function uploadEmployees(
  file: File,
): Promise<EmployeeImportResult> {
  const fd = new FormData();
  fd.append("file", file, file.name);
  const res = await authFetch(`/api/admin/employees/upload`, {
    method: "POST",
    body: fd,
  });
  return jsonOrThrow<EmployeeImportResult>(res);
}

export async function reorderEmployees(
  items: Array<{ id: number; sort_order: number }>,
): Promise<{ updated: number }> {
  const res = await authFetch(`/api/admin/employees/reorder`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items }),
  });
  return jsonOrThrow<{ updated: number }>(res);
}

export async function deleteMasterImage(
  pageId: string,
  blockId: string,
): Promise<void> {
  const res = await authFetch(
    `/api/master-projects/${pageId}/images/${blockId}`,
    { method: "DELETE" },
  );
  if (!res.ok) {
    const detail = await res
      .json()
      .then((d) => (d as { detail?: string }).detail)
      .catch(() => undefined);
    throw new Error(detail ?? `${res.status} ${res.statusText}`);
  }
}

// ── 건의사항 ──

export interface SuggestionItem {
  id: string;
  title: string;
  content: string;
  author: string;
  status: string;
  resolution: string;
  created_time: string | null;
  last_edited_time: string | null;
}

export interface SuggestionListResponse {
  items: SuggestionItem[];
  count: number;
}

export async function listSuggestions(): Promise<SuggestionListResponse> {
  const res = await authFetch(`/api/suggestions`);
  return jsonOrThrow<SuggestionListResponse>(res);
}

export async function createSuggestion(body: {
  title: string;
  content?: string;
}): Promise<SuggestionItem> {
  const res = await authFetch(`/api/suggestions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<SuggestionItem>(res);
}

export async function updateSuggestion(
  id: string,
  body: {
    title?: string;
    content?: string;
    status?: string;
    resolution?: string;
  },
): Promise<SuggestionItem> {
  const res = await authFetch(`/api/suggestions/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<SuggestionItem>(res);
}

export async function deleteSuggestion(id: string): Promise<void> {
  const res = await authFetch(`/api/suggestions/${id}`, { method: "DELETE" });
  if (!res.ok) {
    const detail = await res
      .json()
      .then((d) => (d as { detail?: string }).detail)
      .catch(() => undefined);
    throw new Error(detail ?? `${res.status} ${res.statusText}`);
  }
}

// ── 날인요청 ──

export interface SealAttachment {
  name: string;
  drive_file_id?: string;
  storage_key?: string;
  size?: number;
  content_type?: string;
  legacy_url?: string;
}

export interface SealRequestItem {
  id: string;
  title: string;
  project_ids: string[];
  seal_type: string;
  status: string;
  requester: string;
  lead_handler: string;
  admin_handler: string;
  requested_at: string | null;
  lead_handled_at: string | null;
  admin_handled_at: string | null;
  due_date: string | null;
  note: string;
  attachments: SealAttachment[];
  // docs/request.md 추가 컬럼
  // 실제출처: 거래처 DB relation. 이름은 frontend useClients hook으로 lookup.
  real_source_id: string;
  purpose: string;
  revision: number | null;
  with_safety_cert: boolean;
  summary: string;
  doc_no: string;
  doc_kind: string;
  folder_url: string;
  reject_reason: string;
  linked_task_id: string;
  created_time: string | null;
  last_edited_time: string | null;
}

export interface SealUpdateBody {
  title?: string;
  real_source_id?: string;
  purpose?: string;
  revision?: number;
  with_safety_cert?: boolean;
  summary?: string;
  doc_kind?: string;
  note?: string;
  due_date?: string;
}

export interface SealListResponse {
  items: SealRequestItem[];
  count: number;
}

export async function listSealRequests(
  filters: { projectId?: string } = {},
): Promise<SealListResponse> {
  const res = await authFetch(
    `/api/seal-requests${qs({ project_id: filters.projectId })}`,
  );
  return jsonOrThrow<SealListResponse>(res);
}

export async function getSealPendingCount(): Promise<{ count: number }> {
  const res = await authFetch(`/api/seal-requests/pending-count`);
  return jsonOrThrow<{ count: number }>(res);
}

export async function getNextSealDocNumber(
  sealType: string,
): Promise<{ seal_type: string; next_doc_number: string }> {
  const res = await authFetch(
    `/api/seal-requests/next-doc-number${qs({ seal_type: sealType })}`,
  );
  return jsonOrThrow<{ seal_type: string; next_doc_number: string }>(res);
}

export interface ReviewFolderState {
  ymd: string;
  exists: boolean;
  folder_url: string;
  folder_id: string;
  file_count: number;
}

export async function getReviewFolder(
  projectId: string,
): Promise<ReviewFolderState> {
  const res = await authFetch(`/api/projects/${projectId}/review-folder`);
  return jsonOrThrow<ReviewFolderState>(res);
}

export async function createReviewFolder(
  projectId: string,
): Promise<ReviewFolderState> {
  const res = await authFetch(`/api/projects/${projectId}/review-folder`, {
    method: "POST",
  });
  return jsonOrThrow<ReviewFolderState>(res);
}

export async function deleteDriveFile(
  projectId: string,
  fileId: string,
): Promise<void> {
  const res = await authFetch(
    `/api/projects/${projectId}/drive/files/${fileId}`,
    { method: "DELETE" },
  );
  if (!res.ok) {
    const detail = await res
      .json()
      .then((d) => (d as { detail?: string }).detail)
      .catch(() => undefined);
    throw new Error(detail ?? `${res.status} ${res.statusText}`);
  }
}

export async function createSealRequest(form: FormData): Promise<SealRequestItem> {
  // multipart/form-data: project_id, seal_type, title?, note, files[]
  const res = await authFetch(`/api/seal-requests`, {
    method: "POST",
    body: form,
  });
  return jsonOrThrow<SealRequestItem>(res);
}

export interface SealRedoRequest {
  seal_type: string;
  due_date: string;
  title?: string;
  note?: string;
  real_source_id?: string;
  purpose?: string;
  revision?: number;
  with_safety_cert?: boolean;
  summary?: string;
  doc_kind?: string;
}

export async function redoSealRequest(
  id: string,
  body: SealRedoRequest,
): Promise<SealRequestItem> {
  const res = await authFetch(`/api/seal-requests/${id}/redo`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<SealRequestItem>(res);
}

export async function approveSealLead(id: string): Promise<SealRequestItem> {
  const res = await authFetch(`/api/seal-requests/${id}/approve-lead`, {
    method: "PATCH",
  });
  return jsonOrThrow<SealRequestItem>(res);
}

export async function approveSealAdmin(id: string): Promise<SealRequestItem> {
  const res = await authFetch(`/api/seal-requests/${id}/approve-admin`, {
    method: "PATCH",
  });
  return jsonOrThrow<SealRequestItem>(res);
}

export async function rejectSealRequest(
  id: string,
  reason: string,
): Promise<SealRequestItem> {
  const res = await authFetch(`/api/seal-requests/${id}/reject`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason }),
  });
  return jsonOrThrow<SealRequestItem>(res);
}

/** 재요청용 텍스트 필드 update (반려 또는 1차검토 중일 때만). */
export async function updateSealRequest(
  id: string,
  body: SealUpdateBody,
): Promise<SealRequestItem> {
  const res = await authFetch(`/api/seal-requests/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<SealRequestItem>(res);
}

/** 반려된 요청을 보완해 추가 파일 업로드 (상태 자동으로 '1차검토 중'으로 되돌림). */
export async function addSealAttachments(
  id: string,
  files: File[],
): Promise<SealRequestItem> {
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  const res = await authFetch(`/api/seal-requests/${id}/attachments`, {
    method: "POST",
    body: fd,
  });
  return jsonOrThrow<SealRequestItem>(res);
}

/** 첨부파일 fresh URL 가져오기 (노션 signed URL 1시간 만료 우회). */
export async function getSealAttachmentUrl(
  id: string,
  idx: number,
): Promise<{ url: string; name: string }> {
  const res = await authFetch(`/api/seal-requests/${id}/download/${idx}`);
  return jsonOrThrow<{ url: string; name: string }>(res);
}

export async function deleteSealRequest(id: string): Promise<void> {
  const res = await authFetch(`/api/seal-requests/${id}`, { method: "DELETE" });
  if (!res.ok) {
    const detail = await res
      .json()
      .then((d) => (d as { detail?: string }).detail)
      .catch(() => undefined);
    throw new Error(detail ?? `${res.status} ${res.statusText}`);
  }
}

// ── WORKS Drive 임베디드 탐색기 ──

export async function listDriveChildren(
  projectId: string,
  folderId?: string,
  cursor?: string,
): Promise<DriveChildrenResponse> {
  const q = qs({ folder_id: folderId, cursor });
  const res = await authFetch(
    `/api/projects/${encodeURIComponent(projectId)}/drive/children${q}`,
  );
  return jsonOrThrow<DriveChildrenResponse>(res);
}

export async function getDriveDownloadUrl(
  projectId: string,
  fileId: string,
): Promise<{ url: string; fileName: string }> {
  const res = await authFetch(
    `/api/projects/${encodeURIComponent(projectId)}/drive/download/${encodeURIComponent(fileId)}`,
  );
  return jsonOrThrow<{ url: string; fileName: string }>(res);
}

/** short-lived stream token 발급 + backend stream URL 조립.
 * 반환 URL은 GET 시 Content-Disposition: attachment로 강제 다운로드.
 */
export async function getDriveStreamUrl(
  projectId: string,
  fileId: string,
  fileName?: string,
): Promise<string> {
  const res = await authFetch(
    `/api/projects/${encodeURIComponent(projectId)}/drive/issue-token/${encodeURIComponent(fileId)}`,
  );
  const { token } = await jsonOrThrow<{ token: string }>(res);
  const params = new URLSearchParams({ token });
  if (fileName) params.set("name", fileName);
  return `${API_BASE}/api/projects/${encodeURIComponent(projectId)}/drive/stream/${encodeURIComponent(fileId)}?${params.toString()}`;
}

export async function uploadDriveFiles(
  projectId: string,
  folderId: string | undefined,
  files: File[] | FileList,
): Promise<DriveUploadResponse> {
  const fd = new FormData();
  const arr = Array.from(files as FileList);
  for (const f of arr) fd.append("files", f, f.name);
  const q = qs({ folder_id: folderId });
  const res = await authFetch(
    `/api/projects/${encodeURIComponent(projectId)}/drive/upload${q}`,
    { method: "POST", body: fd },
  );
  return jsonOrThrow<DriveUploadResponse>(res);
}

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
  code: string;
  category: string[];
  name: string;
  client: string;
  scale: string;
  estimated_amount: number | null;
  is_bid: boolean;
  stage: string;
  submission_date: string | null;
  sales_start_date: string | null;     // 영업시작일 (PR-W)
}

export interface WeeklyCompletedItem {
  code: string;
  name: string;
  teams: string[];
  assignees: string[];
  client: string;
  status_label: string;     // 완료 | 타절 | 종결
  completed_at: string | null;
}

export interface WeeklyNewProject {
  code: string;
  name: string;
  teams: string[];
  assignees: string[];
  client: string;
  work_types: string[];
  scale: string;
  contract_amount: number | null;
  stage: string;
  started_at: string | null;  // 수주일
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

export interface WeeklySealLogItem {
  project_name: string;
  client: string;
  seal_type: string;
  status: string;
  handler: string;
  due_date: string | null;
  requested_at: string | null;
}

export interface WeeklyPersonalScheduleEntry {
  employee_name: string;
  team: string;
  category: string;
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
}

export interface WeeklyReportRange {
  weekStart: string;            // 이번주 시작일 (월요일 권장)
  weekEnd?: string;             // optional — default: weekStart + 4일
  lastWeekStart?: string;       // optional — default: weekStart - 7일
}

function buildWeeklyReportQuery(range: WeeklyReportRange): string {
  const qs = new URLSearchParams({ week_start: range.weekStart });
  if (range.weekEnd) qs.set("week_end", range.weekEnd);
  if (range.lastWeekStart) qs.set("last_week_start", range.lastWeekStart);
  return qs.toString();
}

export async function fetchWeeklyReport(
  range: WeeklyReportRange,
): Promise<WeeklyReport> {
  const res = await authFetch(`/api/weekly-report?${buildWeeklyReportQuery(range)}`);
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
): Promise<void> {
  await downloadPdfBlob(
    `/api/weekly-report.pdf?${buildWeeklyReportQuery(range)}`,
    `${range.weekStart}_업무일지.pdf`,
  );
}

/** 주간 업무일지 PDF를 Blob으로 가져옴 (iframe 미리보기용).
 * 호출자가 URL.createObjectURL로 변환해 사용하고, 사용 후 revokeObjectURL 책임. */
export async function fetchWeeklyReportPdfBlob(
  range: WeeklyReportRange,
): Promise<Blob> {
  const res = await authFetch(
    `/api/weekly-report.pdf?${buildWeeklyReportQuery(range)}`,
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

// ── 사내 공지 / 교육 일정 (PR-W Phase 2.4) ──

export type NoticeKind = "공지" | "교육" | "휴일";

export interface Notice {
  id: number;
  kind: NoticeKind;
  title: string;
  body: string;
  start_date: string;       // YYYY-MM-DD
  end_date: string | null;
  author_user_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface NoticeListResponse {
  items: Notice[];
  count: number;
}

export interface NoticeCreateBody {
  kind: NoticeKind;
  title: string;
  body?: string;
  start_date: string;
  end_date?: string | null;
}

export interface NoticeUpdateBody {
  kind?: NoticeKind;
  title?: string;
  body?: string;
  start_date?: string;
  end_date?: string | null;
}

export async function listNotices(params?: {
  weekStart?: string;
  kind?: NoticeKind;
}): Promise<NoticeListResponse> {
  const qs = new URLSearchParams();
  if (params?.weekStart) qs.set("week_start", params.weekStart);
  if (params?.kind) qs.set("kind", params.kind);
  const url = `/api/notices${qs.toString() ? `?${qs.toString()}` : ""}`;
  const res = await authFetch(url);
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      (detail as { detail?: string } | null)?.detail ??
        `${res.status} ${res.statusText}`,
    );
  }
  return (await res.json()) as NoticeListResponse;
}

export async function createNotice(body: NoticeCreateBody): Promise<Notice> {
  const res = await authFetch("/api/notices", {
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
  return (await res.json()) as Notice;
}

export async function updateNotice(
  id: number,
  body: NoticeUpdateBody,
): Promise<Notice> {
  const res = await authFetch(`/api/notices/${id}`, {
    method: "PATCH",
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
  return (await res.json()) as Notice;
}

export async function deleteNotice(id: number): Promise<void> {
  const res = await authFetch(`/api/notices/${id}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      (detail as { detail?: string } | null)?.detail ??
        `${res.status} ${res.statusText}`,
    );
  }
}
