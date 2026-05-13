// /api/auth/users — 사용자 관리 (admin)
import type { UserInfo, UserRole } from "@/lib/types";

import { authFetch, jsonOrThrow } from "./_internal";

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
