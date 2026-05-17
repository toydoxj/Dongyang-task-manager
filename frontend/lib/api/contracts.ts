// /api/contracts — 프로젝트 계약서 메타 + Drive 파일 (PR-FH/2)
import type { Contract, ContractListResponse } from "@/lib/domain";

import { authFetch, jsonOrThrow } from "./_internal";

export interface ContractCreateRequest {
  project_id: string;
  title?: string;
  signed_date?: string | null; // YYYY-MM-DD
  start_date?: string | null;
  end_date?: string | null;
  amount?: number | null;
  vat_included?: boolean;
  note?: string;
  client_id?: string | null;  // PR-FI/4
}

export interface ContractUpdateRequest {
  title?: string;
  signed_date?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  amount?: number | null;
  vat_included?: boolean;
  note?: string;
  client_id?: string | null;  // PR-FI/4
}

export interface ContractListFilters {
  project_id?: string;
  client_id?: string;
  q?: string;
  year?: number;
  offset?: number;
  limit?: number;
}

function buildQuery(filters?: ContractListFilters): string {
  if (!filters) return "";
  const params = new URLSearchParams();
  if (filters.project_id) params.set("project_id", filters.project_id);
  if (filters.client_id) params.set("client_id", filters.client_id);
  if (filters.q) params.set("q", filters.q);
  if (filters.year != null) params.set("year", String(filters.year));
  if (filters.offset != null) params.set("offset", String(filters.offset));
  if (filters.limit != null) params.set("limit", String(filters.limit));
  const s = params.toString();
  return s ? `?${s}` : "";
}

export async function listContracts(
  filters?: ContractListFilters,
): Promise<ContractListResponse> {
  const res = await authFetch(`/api/contracts${buildQuery(filters)}`);
  return jsonOrThrow<ContractListResponse>(res);
}

export async function getContract(id: number): Promise<Contract> {
  const res = await authFetch(`/api/contracts/${id}`);
  return jsonOrThrow<Contract>(res);
}

export async function createContract(
  body: ContractCreateRequest,
): Promise<Contract> {
  const res = await authFetch(`/api/contracts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<Contract>(res);
}

export async function patchContract(
  id: number,
  body: ContractUpdateRequest,
): Promise<Contract> {
  const res = await authFetch(`/api/contracts/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<Contract>(res);
}

export async function deleteContract(id: number): Promise<void> {
  const res = await authFetch(`/api/contracts/${id}`, { method: "DELETE" });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `삭제 실패 (${res.status})`);
  }
}

export async function uploadContractFile(
  id: number,
  file: File,
): Promise<Contract> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await authFetch(`/api/contracts/${id}/file`, {
    method: "POST",
    body: fd,
  });
  return jsonOrThrow<Contract>(res);
}

export async function deleteContractFile(id: number): Promise<Contract> {
  const res = await authFetch(`/api/contracts/${id}/file`, {
    method: "DELETE",
  });
  return jsonOrThrow<Contract>(res);
}
