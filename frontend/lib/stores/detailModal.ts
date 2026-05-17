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
const listeners = new Set<() => void>();

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

function getSnapshot(): string | null {
  return _projectId;
}

function getServerSnapshot(): string | null {
  return null;
}

function notify(): void {
  for (const l of listeners) l();
}

export function openProjectModal(id: string): void {
  if (!id) return;
  _projectId = id;
  notify();
}

export function closeProjectModal(): void {
  _projectId = null;
  notify();
}

/** 현재 열린 프로젝트 모달 id (없으면 null). */
export function useProjectModalId(): string | null {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
