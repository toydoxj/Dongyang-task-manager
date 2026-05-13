// /api/cashflow — 수금/지출 시계열 + 수금 CRUD
import type { CashflowEntry, CashflowResponse } from "@/lib/domain";

import { authFetch, jsonOrThrow, qs } from "./_internal";

export async function getCashflow(filters: {
  project_id?: string;
  date_from?: string;
  date_to?: string;
  flow?: "income" | "expense" | "all";
} = {}): Promise<CashflowResponse> {
  const res = await authFetch(`/api/cashflow${qs(filters)}`);
  return jsonOrThrow<CashflowResponse>(res);
}

// 수금 CRUD (admin + manager — PR-AB)

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
