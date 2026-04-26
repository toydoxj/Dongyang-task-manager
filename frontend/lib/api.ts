// 백엔드 호출 헬퍼 — 인증 토큰 자동 주입 + JSON 파싱 + 에러 메시지 통일.

import { authFetch } from "./auth";
import type {
  CashflowResponse,
  ClientListResponse,
  MasterImage,
  MasterImageList,
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

export async function assignMe(pageId: string): Promise<Project> {
  const res = await authFetch(`/api/projects/${pageId}/assign`, {
    method: "POST",
  });
  return jsonOrThrow<Project>(res);
}

export async function unassignMe(pageId: string): Promise<Project> {
  const res = await authFetch(`/api/projects/${pageId}/assign`, {
    method: "DELETE",
  });
  return jsonOrThrow<Project>(res);
}

export async function createProject(
  body: ProjectCreateRequest,
): Promise<Project> {
  const res = await authFetch(`/api/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<Project>(res);
}

export async function syncProjectStage(pageId: string): Promise<Project> {
  const res = await authFetch(`/api/projects/${pageId}/sync-stage`, {
    method: "POST",
  });
  return jsonOrThrow<Project>(res);
}

// ── 업무TASK ──

export async function listTasks(filters: {
  project_id?: string;
  assignee?: string;
  status?: string;
  mine?: boolean;
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
