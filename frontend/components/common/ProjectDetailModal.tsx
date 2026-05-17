"use client";

/**
 * PR-FR — 글로벌 프로젝트 상세 모달.
 *
 * `<ProjectDetailModal />`을 AppShell에 1회 mount. `openProjectModal(id)`가
 * detailModal store id를 set하면 ProjectClient를 overlay로 표시.
 * 닫기(X / ESC / 백드롭) → `closeProjectModal()`.
 *
 * ProjectClient의 자체 헤더 닫기 버튼(goBack)은 prop `onCloseOverride`로
 * `closeProjectModal`로 매핑 → modal context에서 router.back() 회피.
 */

import { useEffect } from "react";

import ProjectClient from "@/app/project/ProjectClient";
import {
  closeProjectModal,
  useProjectModalId,
} from "@/lib/stores/detailModal";

export default function ProjectDetailModal() {
  const projectId = useProjectModalId();

  useEffect(() => {
    if (!projectId) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeProjectModal();
    };
    window.addEventListener("keydown", onKey);
    // 모달 open 시 body scroll lock
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [projectId]);

  if (!projectId) return null;

  return (
    <div
      className="fixed inset-0 z-50 overflow-y-auto bg-black/60 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="프로젝트 상세"
    >
      <div className="flex min-h-full items-start justify-center p-4 sm:p-6">
        <div className="relative w-full max-w-[1400px] rounded-2xl bg-white shadow-2xl dark:bg-zinc-900">
          <button
            type="button"
            onClick={closeProjectModal}
            aria-label="닫기"
            className="absolute right-3 top-3 z-10 rounded-md bg-white/80 p-1.5 text-zinc-500 backdrop-blur hover:bg-zinc-100 hover:text-zinc-900 dark:bg-zinc-900/80 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              className="h-5 w-5"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
          <div className="p-4 sm:p-6">
            <ProjectClient
              id={projectId}
              onCloseOverride={closeProjectModal}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
