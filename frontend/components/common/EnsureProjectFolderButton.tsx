"use client";

/**
 * PR-FV — 프로젝트 WORKS Drive 폴더가 없을 때 「만들기」 버튼.
 *
 * 사용처: 계약서/검토서 등록 모달에서 프로젝트를 선택했는데 그 프로젝트의
 * Drive 폴더가 아직 만들어지지 않은 경우 (구 프로젝트 또는 자동 생성 실패).
 * 사용자가 폴더 부재를 인지하고 한 번에 만들 수 있도록 노란 경고 박스 + 버튼.
 *
 * 동작:
 * - project.drive_url 있으면 null return (조용함)
 * - 없으면 경고 박스 + 「프로젝트 폴더 만들기」 버튼 노출
 * - 클릭 → ensureProjectDriveFolder(project.id) → 성공 시 onCreated callback
 */

import { useState } from "react";

import type { Project } from "@/lib/domain";
import { ensureProjectDriveFolder } from "@/lib/api";

interface Props {
  project: Project | null | undefined;
  /** 폴더 생성 성공 시 호출 — caller가 자신의 selected project state를 update. */
  onCreated?: (updated: Project) => void;
}

export default function EnsureProjectFolderButton({ project, onCreated }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!project) return null;
  // PR-GH: 폴더 있음을 명시적으로 표시 (사용자 요청 — 「드라이브 개설 확인」 흐름).
  if (project.drive_url) {
    return (
      <div className="mt-2 flex items-center justify-between gap-2 rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-xs dark:border-emerald-700 dark:bg-emerald-950/40">
        <span className="flex items-center gap-1.5 text-emerald-800 dark:text-emerald-300">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            className="h-3.5 w-3.5"
          >
            <polyline points="20 6 9 17 4 12" />
          </svg>
          WORKS Drive 폴더 준비됨
        </span>
        <a
          href={project.drive_url}
          target="_blank"
          rel="noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="shrink-0 text-emerald-700 underline-offset-2 hover:underline dark:text-emerald-300"
        >
          폴더 열기 ↗
        </a>
      </div>
    );
  }

  const handleClick = async (): Promise<void> => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await ensureProjectDriveFolder(project.id);
      // SWR 캐시 갱신은 caller가 자체 mutate로 처리 (project list/상세 key 구조에 의존).
      onCreated?.(updated);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "폴더 생성 실패");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs dark:border-amber-700 dark:bg-amber-950/40">
      <div className="flex items-center justify-between gap-2">
        <span className="text-amber-800 dark:text-amber-300">
          이 프로젝트는 WORKS Drive 폴더가 아직 없습니다.
          첨부 업로드 전에 폴더를 먼저 만들어야 합니다.
        </span>
        <button
          type="button"
          onClick={handleClick}
          disabled={busy}
          className="shrink-0 rounded-md border border-amber-400 bg-white px-3 py-1 text-amber-800 hover:bg-amber-100 disabled:opacity-50 dark:bg-zinc-900 dark:text-amber-200 dark:hover:bg-zinc-800"
        >
          {busy ? "생성 중…" : "프로젝트 폴더 만들기"}
        </button>
      </div>
      {error && (
        <p className="mt-1 text-[11px] text-red-700 dark:text-red-400">{error}</p>
      )}
    </div>
  );
}
