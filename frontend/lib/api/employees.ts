// /api/admin/employees — 직원 명부 (admin + team_lead + manager — PR-AT)
import type {
  Employee,
  EmployeeCreate,
  EmployeeImportResult,
  EmployeeListResponse,
  EmployeeUpdate,
  EmployeeView,
} from "@/lib/domain";

import { authFetch, jsonOrThrow, qs } from "./_internal";

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
