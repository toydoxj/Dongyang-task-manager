// /api/master-projects — 마스터 프로젝트(포트폴리오) + 이미지
import type {
  MasterImage,
  MasterImageList,
  MasterOptions,
  MasterProject,
  MasterProjectUpdate,
} from "@/lib/domain";

import { authFetch, jsonOrThrow } from "./_internal";

export async function getMasterProject(pageId: string): Promise<MasterProject> {
  const res = await authFetch(`/api/master-projects/${pageId}`);
  return jsonOrThrow<MasterProject>(res);
}

export async function getMasterOptions(): Promise<MasterOptions> {
  const res = await authFetch(`/api/master-projects/options`);
  return jsonOrThrow<MasterOptions>(res);
}

export async function updateMasterProject(
  pageId: string,
  body: MasterProjectUpdate,
): Promise<MasterProject> {
  const res = await authFetch(`/api/master-projects/${pageId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<MasterProject>(res);
}

export async function listMasterImages(
  pageId: string,
): Promise<MasterImageList> {
  const res = await authFetch(`/api/master-projects/${pageId}/images`);
  return jsonOrThrow<MasterImageList>(res);
}

export async function uploadMasterImage(
  pageId: string,
  file: File,
  caption: string = "",
): Promise<MasterImage> {
  const fd = new FormData();
  fd.append("file", file, file.name);
  if (caption) fd.append("caption", caption);
  const res = await authFetch(`/api/master-projects/${pageId}/images`, {
    method: "POST",
    body: fd,
  });
  return jsonOrThrow<MasterImage>(res);
}

export async function deleteMasterImage(
  pageId: string,
  blockId: string,
): Promise<void> {
  const res = await authFetch(
    `/api/master-projects/${pageId}/images/${blockId}`,
    { method: "DELETE" },
  );
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `삭제 실패 (${res.status})`);
  }
}
