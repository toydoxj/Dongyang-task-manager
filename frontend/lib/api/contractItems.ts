// /api/contract-items — 공동수급/추가용역
import type { ContractItem, ContractItemListResponse } from "@/lib/domain";

import { authFetch, jsonOrThrow } from "./_internal";

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
