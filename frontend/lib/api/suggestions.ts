// 건의사항 API — listSuggestions / create / update / delete.

import { authFetch, jsonOrThrow } from "./_internal";

export interface SuggestionItem {
  id: string;
  title: string;
  content: string;
  author: string;
  categories: string[];  // PR-CO: 노션 "구분" multi_select
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
  categories?: string[];
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
    categories?: string[];
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
