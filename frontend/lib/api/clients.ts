// 발주처(client) API — listClients, createClient, updateClient, deleteClient.

import type { Client, ClientListResponse } from "@/lib/domain";

import { authFetch, jsonOrThrow } from "./_internal";

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
