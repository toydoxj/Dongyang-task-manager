// /api/sales — 영업/견적 CRUD + 견적 PDF + 외부 견적 + 묶음 PDF
import type {
  Project,
  QuoteFormResponse,
  QuoteInput,
  QuoteResult,
  Sale,
  SaleCreateRequest,
  SaleListResponse,
  SaleUpdateRequest,
} from "@/lib/domain";

import { authFetch, downloadPdfBlob, jsonOrThrow, qs } from "./_internal";

export async function listSales(
  filters: {
    assignee?: string;
    kind?: string;
    stage?: string;
    mine?: boolean;
    /** PR-EC (4-C): pagination. 미지정 시 backend는 unbounded 반환. */
    offset?: number;
    /** 1~500. 미지정 시 backend unbounded. */
    limit?: number;
  } = {},
): Promise<SaleListResponse> {
  const res = await authFetch(`/api/sales${qs(filters)}`);
  return jsonOrThrow<SaleListResponse>(res);
}

export async function getSale(pageId: string): Promise<Sale> {
  const res = await authFetch(`/api/sales/${pageId}`);
  return jsonOrThrow<Sale>(res);
}

export async function createSale(body: SaleCreateRequest): Promise<Sale> {
  const res = await authFetch(`/api/sales`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<Sale>(res);
}

export async function updateSale(
  pageId: string,
  body: SaleUpdateRequest,
): Promise<Sale> {
  const res = await authFetch(`/api/sales/${pageId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<Sale>(res);
}

export async function archiveSale(
  pageId: string,
): Promise<{ status: string; page_id: string }> {
  const res = await authFetch(`/api/sales/${pageId}`, { method: "DELETE" });
  return jsonOrThrow<{ status: string; page_id: string }>(res);
}

/** 수주영업·우선협상/낙찰 단계의 영업을 메인 프로젝트로 전환. admin 전용. */
export async function convertSale(pageId: string): Promise<Project> {
  const res = await authFetch(`/api/sales/${pageId}/convert`, { method: "POST" });
  return jsonOrThrow<Project>(res);
}

/** 영업을 기존 진행 프로젝트에 수동 연결. admin 전용.
 * 영업의 단계가 '완료'로 자동 변경되고 전환된 프로젝트 relation이 채워진다.
 */
export async function linkSaleToProject(
  pageId: string,
  projectId: string,
): Promise<Sale> {
  const res = await authFetch(`/api/sales/${pageId}/link-project`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: projectId }),
  });
  return jsonOrThrow<Sale>(res);
}

/** 프로젝트 id로 연결된 영업(Sale) reverse lookup. 없으면 null. */
export async function findSaleByProject(projectId: string): Promise<Sale | null> {
  const res = await authFetch(`/api/sales/by-project/${projectId}`);
  if (!res.ok) {
    if (res.status === 404) return null;
    throw new Error(`${res.status} ${res.statusText}`);
  }
  // backend가 null을 그대로 직렬화하면 응답이 "null" 문자열
  const body = await res.text();
  if (!body || body === "null") return null;
  return JSON.parse(body) as Sale;
}

/** 견적서 산출 미리보기 (저장 X) — 입력 변경 시 디바운스 호출. */
export async function previewQuote(input: QuoteInput): Promise<QuoteResult> {
  const res = await authFetch(`/api/sales/quote/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return jsonOrThrow<QuoteResult>(res);
}

/** 단일 견적 PDF → WORKS Drive [견적서]/{YYYY}년 자동 업로드 + 노션 sale 견적서첨부 갱신.
 * quoteId 미지정 시 첫 견적 (legacy 호환). */
export async function saveQuotePdfToDrive(
  saleId: string,
  quoteId?: string,
): Promise<Sale> {
  const queryStr = quoteId ? `?quote_id=${encodeURIComponent(quoteId)}` : "";
  const res = await authFetch(
    `/api/sales/${saleId}/quote/save-pdf-to-drive${queryStr}`,
    { method: "POST" },
  );
  return jsonOrThrow<Sale>(res);
}

/** 단일 견적 PDF 다운로드. quoteId 미지정 시 첫 견적 (legacy 호환). */
export async function downloadQuotePdf(
  saleId: string,
  quoteId?: string,
): Promise<void> {
  const queryStr = quoteId ? `?quote_id=${encodeURIComponent(quoteId)}` : "";
  await downloadPdfBlob(`/api/sales/${saleId}/quote.pdf${queryStr}`, "quote.pdf");
}

/** 영업의 모든 견적 list (PR-M1). */
export async function listSaleQuotes(
  saleId: string,
): Promise<QuoteFormResponse[]> {
  const res = await authFetch(`/api/sales/${saleId}/quotes`);
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      (detail as { detail?: string } | null)?.detail ??
        `${res.status} ${res.statusText}`,
    );
  }
  return (await res.json()) as QuoteFormResponse[];
}

/** 영업에 견적 1건 추가 (PR-M1). suffix·doc_number 자동 부여. */
export async function addSaleQuote(
  saleId: string,
  input: QuoteInput,
): Promise<QuoteFormResponse> {
  const res = await authFetch(`/api/sales/${saleId}/quotes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      (detail as { detail?: string } | null)?.detail ??
        `${res.status} ${res.statusText}`,
    );
  }
  return (await res.json()) as QuoteFormResponse;
}

/** 견적 수정 — input/result만 갱신, doc_number/suffix 보존 (PR-M1). */
export async function updateSaleQuote(
  saleId: string,
  quoteId: string,
  input: QuoteInput,
): Promise<QuoteFormResponse> {
  const res = await authFetch(`/api/sales/${saleId}/quotes/${quoteId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      (detail as { detail?: string } | null)?.detail ??
        `${res.status} ${res.statusText}`,
    );
  }
  return (await res.json()) as QuoteFormResponse;
}

/** 외부 견적 추가 (PR-EXT) — 산출 X, 금액만. 갑지 row만 표시. */
export async function addSaleExternalQuote(
  saleId: string,
  body: { service: string; amount: number; vat_included?: boolean },
): Promise<QuoteFormResponse> {
  const res = await authFetch(`/api/sales/${saleId}/quotes/external`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      (detail as { detail?: string } | null)?.detail ??
        `${res.status} ${res.statusText}`,
    );
  }
  return (await res.json()) as QuoteFormResponse;
}

/** 외부 견적 service/amount 수정 (PR-EXT). 첨부 PDF 보존. */
export async function updateSaleExternalQuote(
  saleId: string,
  quoteId: string,
  body: { service: string; amount: number; vat_included?: boolean },
): Promise<QuoteFormResponse> {
  const res = await authFetch(
    `/api/sales/${saleId}/quotes/external/${quoteId}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      (detail as { detail?: string } | null)?.detail ??
        `${res.status} ${res.statusText}`,
    );
  }
  return (await res.json()) as QuoteFormResponse;
}

/** 외부 견적 PDF 첨부 (PR-EXT-2) — multipart upload → Drive [견적서]/{YYYY}년/.
 * form.attached_pdf_url/name/file_id 갱신. 갑지 표에 첨부 → 링크 노출. */
export async function attachExternalQuotePdf(
  saleId: string,
  quoteId: string,
  file: File,
): Promise<QuoteFormResponse> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await authFetch(
    `/api/sales/${saleId}/quotes/external/${quoteId}/attach-pdf`,
    { method: "POST", body: fd },
  );
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      (detail as { detail?: string } | null)?.detail ??
        `${res.status} ${res.statusText}`,
    );
  }
  return (await res.json()) as QuoteFormResponse;
}

/** 견적 문서번호 수동 수정. suffix/input/result 보존. */
export async function updateQuoteDocNumber(
  saleId: string,
  quoteId: string,
  docNumber: string,
): Promise<QuoteFormResponse> {
  const res = await authFetch(
    `/api/sales/${saleId}/quotes/${quoteId}/doc-number`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ doc_number: docNumber }),
    },
  );
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      (detail as { detail?: string } | null)?.detail ??
        `${res.status} ${res.statusText}`,
    );
  }
  return (await res.json()) as QuoteFormResponse;
}

/** 견적 삭제 (PR-M1). suffix 재할당 X — hole 보존. */
export async function deleteSaleQuote(
  saleId: string,
  quoteId: string,
): Promise<void> {
  const res = await authFetch(`/api/sales/${saleId}/quotes/${quoteId}`, {
    method: "DELETE",
  });
  if (!res.ok && res.status !== 204) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      (detail as { detail?: string } | null)?.detail ??
        `${res.status} ${res.statusText}`,
    );
  }
}

/** 통합 견적서 PDF 다운로드 — parent_lead_id로 묶인 자식들과 함께 1 PDF (PR-G1).
 * showTotal=false면 갑지에 견적가 + 합계 row 숨김. */
export async function downloadQuoteBundlePdf(
  parentSaleId: string,
  showTotal: boolean = true,
): Promise<void> {
  await downloadPdfBlob(
    `/api/sales/${parentSaleId}/quote-bundle.pdf?show_total=${showTotal ? "true" : "false"}`,
    "quote-bundle.pdf",
  );
}

/** 통합 견적서 PDF를 WORKS Drive에 자동 저장 (PR-G2). parent의 `통합견적서첨부`
 * 컬럼에 web url 저장. 단일 PDF (`견적서첨부`)는 그대로 보존. */
export async function saveQuoteBundlePdfToDrive(
  parentSaleId: string,
  showTotal: boolean = true,
): Promise<Sale> {
  const res = await authFetch(
    `/api/sales/${parentSaleId}/quote-bundle/save-pdf-to-drive?show_total=${showTotal ? "true" : "false"}`,
    { method: "POST" },
  );
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      (detail as { detail?: string } | null)?.detail ??
        `${res.status} ${res.statusText}`,
    );
  }
  return (await res.json()) as Sale;
}
