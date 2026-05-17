"use client";

/**
 * PR-FR — 프로젝트 상세 글로벌 모달 store.
 *
 * 별도 윈도우(PR-FN~FQ window.open 팝업) 대신, 현재 페이지 위에 떠 있는 모달
 * overlay로 전환 (사용자 요구). PopupLinks / ProjectCard / 향후 13곳에서
 * `openProjectModal(id)` 호출 → `<ProjectDetailModal />` (AppShell mount) 표시.
 *
 * zustand 미설치 — useSyncExternalStore로 외부 store 구현 (deps 추가 회피).
 * 향후 sale·contract·employee 등 동일 패턴 추가 시 이 파일에 확장.
 */

import { useSyncExternalStore } from "react";

let _projectId: string | null = null;
let _saleId: string | null = null;
const projectListeners = new Set<() => void>();
const saleListeners = new Set<() => void>();

function subscribeProject(cb: () => void): () => void {
  projectListeners.add(cb);
  return () => {
    projectListeners.delete(cb);
  };
}
function subscribeSale(cb: () => void): () => void {
  saleListeners.add(cb);
  return () => {
    saleListeners.delete(cb);
  };
}

function getProjectSnapshot(): string | null {
  return _projectId;
}
function getSaleSnapshot(): string | null {
  return _saleId;
}

function getServerSnapshot(): string | null {
  return null;
}

function notifyProject(): void {
  for (const l of projectListeners) l();
}
function notifySale(): void {
  for (const l of saleListeners) l();
}

export function openProjectModal(id: string): void {
  if (!id) return;
  _projectId = id;
  notifyProject();
}

export function closeProjectModal(): void {
  _projectId = null;
  notifyProject();
}

/** 현재 열린 프로젝트 모달 id (없으면 null). */
export function useProjectModalId(): string | null {
  return useSyncExternalStore(subscribeProject, getProjectSnapshot, getServerSnapshot);
}

export function openSaleModal(id: string): void {
  if (!id) return;
  _saleId = id;
  notifySale();
}

export function closeSaleModal(): void {
  _saleId = null;
  notifySale();
}

/** 현재 열린 영업 모달 id (없으면 null). */
export function useSaleModalId(): string | null {
  return useSyncExternalStore(subscribeSale, getSaleSnapshot, getServerSnapshot);
}
