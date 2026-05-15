// /api/seal-requests + Drive 보조 (review-folder, drive file delete)
import { authFetch, jsonOrThrow, qs } from "./_internal";

export interface SealAttachment {
  name: string;
  drive_file_id?: string;
  storage_key?: string;
  size?: number;
  content_type?: string;
  legacy_url?: string;
}

/** PR-BX (외부 리뷰 12.x #1): 부분 실패 정형 응답.
 * create / attachments endpoint 응답에 포함될 수 있음. 호출자가 toast로 노출.
 * 비어있으면 정상 또는 silent (logger만).
 */
export interface PartialError {
  code: string;
  target: string;
  message: string;
  retryable: boolean;
}

export interface SealRequestItem {
  id: string;
  title: string;
  project_ids: string[];
  seal_type: string;
  status: string;
  requester: string;
  lead_handler: string;
  admin_handler: string;
  requested_at: string | null;
  lead_handled_at: string | null;
  admin_handled_at: string | null;
  due_date: string | null;
  note: string;
  attachments: SealAttachment[];
  // docs/request.md 추가 컬럼
  // 실제출처: 거래처 DB relation. 이름은 frontend useClients hook으로 lookup.
  real_source_id: string;
  purpose: string;
  revision: number | null;
  with_safety_cert: boolean;
  summary: string;
  doc_no: string;
  doc_kind: string;
  folder_url: string;
  reject_reason: string;
  linked_task_id: string;
  created_time: string | null;
  last_edited_time: string | null;
  /** PR-BX: create / attachments POST 응답에서만 채워짐. list endpoint는 항상 빈 배열. */
  partial_errors?: PartialError[];
}

export interface SealUpdateBody {
  title?: string;
  real_source_id?: string;
  purpose?: string;
  revision?: number;
  with_safety_cert?: boolean;
  summary?: string;
  doc_kind?: string;
  note?: string;
  due_date?: string;
}

export interface SealListResponse {
  items: SealRequestItem[];
  count: number;
}

export async function listSealRequests(
  filters: { projectId?: string } = {},
): Promise<SealListResponse> {
  const res = await authFetch(
    `/api/seal-requests${qs({ project_id: filters.projectId })}`,
  );
  return jsonOrThrow<SealListResponse>(res);
}

export async function getSealPendingCount(): Promise<{ count: number }> {
  const res = await authFetch(`/api/seal-requests/pending-count`);
  return jsonOrThrow<{ count: number }>(res);
}

export async function getNextSealDocNumber(
  sealType: string,
): Promise<{ seal_type: string; next_doc_number: string }> {
  const res = await authFetch(
    `/api/seal-requests/next-doc-number${qs({ seal_type: sealType })}`,
  );
  return jsonOrThrow<{ seal_type: string; next_doc_number: string }>(res);
}

export interface ReviewFolderState {
  ymd: string;
  exists: boolean;
  folder_url: string;
  folder_id: string;
  file_count: number;
}

export async function getReviewFolder(
  projectId: string,
): Promise<ReviewFolderState> {
  const res = await authFetch(`/api/projects/${projectId}/review-folder`);
  return jsonOrThrow<ReviewFolderState>(res);
}

export async function createReviewFolder(
  projectId: string,
): Promise<ReviewFolderState> {
  const res = await authFetch(`/api/projects/${projectId}/review-folder`, {
    method: "POST",
  });
  return jsonOrThrow<ReviewFolderState>(res);
}

export async function deleteDriveFile(
  projectId: string,
  fileId: string,
): Promise<void> {
  const res = await authFetch(
    `/api/projects/${projectId}/drive/files/${fileId}`,
    { method: "DELETE" },
  );
  if (!res.ok) {
    const detail = await res
      .json()
      .then((d) => (d as { detail?: string }).detail)
      .catch(() => undefined);
    throw new Error(detail ?? `${res.status} ${res.statusText}`);
  }
}

export async function createSealRequest(form: FormData): Promise<SealRequestItem> {
  // multipart/form-data: project_id, seal_type, title?, note, files[]
  const res = await authFetch(`/api/seal-requests`, {
    method: "POST",
    body: form,
  });
  return jsonOrThrow<SealRequestItem>(res);
}

export interface SealRedoRequest {
  seal_type: string;
  due_date: string;
  title?: string;
  note?: string;
  real_source_id?: string;
  purpose?: string;
  revision?: number;
  with_safety_cert?: boolean;
  summary?: string;
  doc_kind?: string;
}

export async function redoSealRequest(
  id: string,
  body: SealRedoRequest,
): Promise<SealRequestItem> {
  const res = await authFetch(`/api/seal-requests/${id}/redo`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<SealRequestItem>(res);
}

export async function approveSealLead(id: string): Promise<SealRequestItem> {
  const res = await authFetch(`/api/seal-requests/${id}/approve-lead`, {
    method: "PATCH",
  });
  return jsonOrThrow<SealRequestItem>(res);
}

export async function approveSealAdmin(id: string): Promise<SealRequestItem> {
  const res = await authFetch(`/api/seal-requests/${id}/approve-admin`, {
    method: "PATCH",
  });
  return jsonOrThrow<SealRequestItem>(res);
}

export async function rejectSealRequest(
  id: string,
  reason: string,
): Promise<SealRequestItem> {
  const res = await authFetch(`/api/seal-requests/${id}/reject`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason }),
  });
  return jsonOrThrow<SealRequestItem>(res);
}

/** 재요청용 텍스트 필드 update (반려 또는 1차검토 중일 때만). */
export async function updateSealRequest(
  id: string,
  body: SealUpdateBody,
): Promise<SealRequestItem> {
  const res = await authFetch(`/api/seal-requests/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<SealRequestItem>(res);
}

/** 반려된 요청을 보완해 추가 파일 업로드 (상태 자동으로 '1차검토 중'으로 되돌림). */
export async function addSealAttachments(
  id: string,
  files: File[],
): Promise<SealRequestItem> {
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  const res = await authFetch(`/api/seal-requests/${id}/attachments`, {
    method: "POST",
    body: fd,
  });
  return jsonOrThrow<SealRequestItem>(res);
}

/** 첨부파일 fresh URL 가져오기 (노션 signed URL 1시간 만료 우회). */
export async function getSealAttachmentUrl(
  id: string,
  idx: number,
): Promise<{ url: string; name: string }> {
  const res = await authFetch(`/api/seal-requests/${id}/download/${idx}`);
  return jsonOrThrow<{ url: string; name: string }>(res);
}

export async function deleteSealRequest(id: string): Promise<void> {
  const res = await authFetch(`/api/seal-requests/${id}`, { method: "DELETE" });
  if (!res.ok) {
    const detail = await res
      .json()
      .then((d) => (d as { detail?: string }).detail)
      .catch(() => undefined);
    throw new Error(detail ?? `${res.status} ${res.statusText}`);
  }
}
