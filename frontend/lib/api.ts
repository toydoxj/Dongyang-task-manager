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
