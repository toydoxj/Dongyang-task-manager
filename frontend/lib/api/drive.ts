// /api/projects/{id}/drive/* — WORKS Drive 임베디드 탐색기
import type { DriveChildrenResponse, DriveUploadResponse } from "@/lib/domain";
import { API_BASE } from "@/lib/types";

import { authFetch, jsonOrThrow, qs } from "./_internal";

export async function listDriveChildren(
  projectId: string,
  folderId?: string,
  cursor?: string,
): Promise<DriveChildrenResponse> {
  const q = qs({ folder_id: folderId, cursor });
  const res = await authFetch(
    `/api/projects/${encodeURIComponent(projectId)}/drive/children${q}`,
  );
  return jsonOrThrow<DriveChildrenResponse>(res);
}

export async function getDriveDownloadUrl(
  projectId: string,
  fileId: string,
): Promise<{ url: string; fileName: string }> {
  const res = await authFetch(
    `/api/projects/${encodeURIComponent(projectId)}/drive/download/${encodeURIComponent(fileId)}`,
  );
  return jsonOrThrow<{ url: string; fileName: string }>(res);
}

/** short-lived stream token 발급 + backend stream URL 조립.
 * 반환 URL은 GET 시 Content-Disposition: attachment로 강제 다운로드.
 */
export async function getDriveStreamUrl(
  projectId: string,
  fileId: string,
  fileName?: string,
): Promise<string> {
  const res = await authFetch(
    `/api/projects/${encodeURIComponent(projectId)}/drive/issue-token/${encodeURIComponent(fileId)}`,
  );
  const { token } = await jsonOrThrow<{ token: string }>(res);
  const params = new URLSearchParams({ token });
  if (fileName) params.set("name", fileName);
  return `${API_BASE}/api/projects/${encodeURIComponent(projectId)}/drive/stream/${encodeURIComponent(fileId)}?${params.toString()}`;
}

export async function uploadDriveFiles(
  projectId: string,
  folderId: string | undefined,
  files: File[] | FileList,
): Promise<DriveUploadResponse> {
  const fd = new FormData();
  const arr = Array.from(files as FileList);
  for (const f of arr) fd.append("files", f, f.name);
  const q = qs({ folder_id: folderId });
  const res = await authFetch(
    `/api/projects/${encodeURIComponent(projectId)}/drive/upload${q}`,
    { method: "POST", body: fd },
  );
  return jsonOrThrow<DriveUploadResponse>(res);
}
