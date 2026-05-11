"use client";

/**
 * SalesEditModal에서 "기존 프로젝트 연결" 액션 시 떠오르는 picker modal.
 * 진행 중 프로젝트 우선 노출, 검색 시 완료 포함. 상위 50개만 표시.
 *
 * PR-AE — SalesEditModal.tsx에서 추출 (외과적 변경 / 동작 동일).
 */

import { useState } from "react";

import type { Project } from "@/lib/domain";
import { useProjects } from "@/lib/hooks";

import { inputCls } from "./_shared";

interface Props {
  onClose: () => void;
  onPick: (project: Project) => void;
}

export default function ProjectLinkPicker({ onClose, onPick }: Props) {
  const [query, setQuery] = useState("");
  const { data, error } = useProjects();

  const projects = data?.items ?? [];
  const q = query.trim().toLowerCase();
  const filtered = (
    q
      ? projects.filter(
          (p) =>
            p.name.toLowerCase().includes(q) ||
            (p.code ?? "").toLowerCase().includes(q),
        )
      : projects.filter((p) => !p.completed)
  )
    .slice()
    // 정렬: 완료 안 된 것 먼저, 그 다음 code 역순(최신 코드부터). 50개 limit 안에서 예측성 확보.
    .sort((a, b) => {
      if (a.completed !== b.completed) return a.completed ? 1 : -1;
      return (b.code ?? "").localeCompare(a.code ?? "");
    });

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4">
      {/* backdrop click으로 닫지 않음 — X 버튼만 사용. */}
      <div
        className="w-full max-w-lg rounded-lg border border-zinc-200 bg-white shadow-xl dark:border-zinc-700 dark:bg-zinc-900"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
          <h3 className="text-sm font-semibold">기존 프로젝트 연결</h3>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800"
            aria-label="닫기"
          >
            ×
          </button>
        </header>
        <div className="space-y-2 p-3">
          <input
            type="text"
            placeholder="프로젝트명 또는 CODE 검색"
            className={inputCls}
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <p className="text-[10px] text-zinc-500">
            기본은 진행 중인 프로젝트만 표시. 완료된 프로젝트도 연결하려면 검색어를 입력하세요.
          </p>
          {error && (
            <div className="rounded-md border border-red-500/40 bg-red-500/5 p-2 text-xs text-red-500">
              {error instanceof Error ? error.message : String(error)}
            </div>
          )}
          <div className="max-h-[50vh] overflow-y-auto rounded-md border border-zinc-200 dark:border-zinc-800">
            {filtered.length === 0 ? (
              <p className="p-4 text-center text-xs text-zinc-500">
                {q ? "검색 결과 없음" : "진행 중 프로젝트 없음"}
              </p>
            ) : (
              <ul>
                {filtered.slice(0, 50).map((p) => (
                  <li key={p.id}>
                    <button
                      type="button"
                      onClick={() => onPick(p)}
                      className="block w-full border-b border-zinc-100 px-3 py-2 text-left hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-800/50"
                    >
                      <div className="text-sm font-medium">{p.name}</div>
                      <div className="mt-0.5 text-[11px] text-zinc-500">
                        <span className="font-mono">
                          {p.code || p.id.slice(0, 6)}
                        </span>
                        <span className="ml-2">{p.stage}</span>
                        {p.completed && (
                          <span className="ml-2 text-zinc-400">완료</span>
                        )}
                      </div>
                    </button>
                  </li>
                ))}
                {filtered.length > 50 && (
                  <li className="px-3 py-2 text-[11px] text-zinc-500">
                    상위 50개만 표시 — 검색어로 좁혀주세요
                  </li>
                )}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
