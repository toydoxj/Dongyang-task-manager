// 백엔드 호출 헬퍼 — 인증 토큰 자동 주입 + JSON 파싱 + 에러 메시지 통일.

import { authFetch } from "./auth";
import type {
  CashflowResponse,
  ClientListResponse,
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

export async function unassignMe(pageId: string): Promise<Project> {
  const res = await authFetch(`/api/projects/${pageId}/assign`, {
    method: "DELETE",
  });
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

export async function syncProjectStage(pageId: string): Promise<Project> {
  const res = await authFetch(`/api/projects/${pageId}/sync-stage`, {
    method: "POST",
  });
  return jsonOrThrow<Project>(res);
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

// ── 협력업체 ──

export async function listClients(): Promise<ClientListResponse> {
  const res = await authFetch(`/api/clients`);
  return jsonOrThrow<ClientListResponse>(res);
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
  created_time: string | null;
  last_edited_time: string | null;
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

export async function createSealRequest(form: FormData): Promise<SealRequestItem> {
  // multipart/form-data: project_id, seal_type, title?, note, files[]
  const res = await authFetch(`/api/seal-requests`, {
    method: "POST",
    body: form,
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

/** 반려된 요청을 보완해 추가 파일 업로드 (상태 자동으로 '요청'으로 되돌림). */
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
