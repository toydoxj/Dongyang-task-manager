// /api/projects — 프로젝트 CRUD + 담당자 + 단계 + 로그
import type {
  Project,
  ProjectCreateRequest,
  ProjectListResponse,
  ProjectOptions,
  ProjectUpdateRequest,
} from "@/lib/domain";

import { authFetch, jsonOrThrow, qs } from "./_internal";

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
  body: ProjectUpdateRequest,
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
