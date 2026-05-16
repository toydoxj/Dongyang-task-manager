// 업무 TASK API — list/create/update/archive.

import type {
  Task,
  TaskCreateRequest,
  TaskListResponse,
  TaskUpdateRequest,
} from "@/lib/domain";

import { authFetch, jsonOrThrow, qs } from "./_internal";

export async function listTasks(filters: {
  project_id?: string;
  /** 영업 page_id로 필터 (mirror_tasks.sales_ids relation). */
  sale_id?: string;
  assignee?: string;
  status?: string;
  mine?: boolean;
  schedule_only?: boolean;
  /** PR-EC (4-C): pagination. 미지정 시 backend는 unbounded 반환. */
  offset?: number;
  /** 1~500. 미지정 시 backend unbounded. */
  limit?: number;
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
