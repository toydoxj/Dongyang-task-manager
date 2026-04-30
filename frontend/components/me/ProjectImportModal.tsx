"use client";

import { useMemo, useState } from "react";

import Modal from "@/components/ui/Modal";
import { assignMe } from "@/lib/api";
import type { Project } from "@/lib/domain";
import { useProjects } from "@/lib/hooks";
import { cn } from "@/lib/utils";

interface Props {
  open: boolean;
  onClose: () => void;
  onAssigned: () => void;
  myName: string;
  /** 다른 직원 대신 가져오는 모드 (admin/team_lead). 지정 시 backend에 for_user로 전달. */
  forUser?: string;
}

export default function ProjectImportModal({
  open,
  onClose,
  onAssigned,
  myName,
  forUser,
}: Props) {
  const [query, setQuery] = useState("");
  const trimmed = query.trim();
  const searchMode = trimmed.length > 0;

  // 기본(스크롤): 진행중만 — 빠름 (47건 정도)
  const { data: openData, error: openErr } = useProjects(
    { stage: "진행중" },
    open,
  );
  // 검색 모드: 전체 (1500+건, 첫 호출만 5~15초)
  const { data: allData, error: allErr } = useProjects(
    undefined,
    open && searchMode,
  );

  const [busyId, setBusyId] = useState<string | null>(null);
  const [assignErr, setAssignErr] = useState<string | null>(null);

  const candidates = useMemo<Project[]>(() => {
    if (searchMode) {
      if (!allData) return [];
      const q = trimmed.toLowerCase();
      // 검색 모드: 본인 미담당 + (이미 담당이지만 완료된 프로젝트도 = 재활성화 케이스)
      return allData.items
        .filter((p) => !p.assignees.includes(myName) || p.completed)
        .filter((p) => `${p.code} ${p.name}`.toLowerCase().includes(q))
        .slice(0, 100);
    }
    if (!openData) return [];
    return openData.items
      .filter((p) => !p.completed && !p.assignees.includes(myName))
      .slice(0, 50);
  }, [searchMode, openData, allData, trimmed, myName]);

  const handleAssign = async (p: Project): Promise<void> => {
    // 진행단계가 "진행중"이 아니면 사용자 확인 후 "대기"로 자동 전환
    let setToWaiting = false;
    if (p.stage !== "진행중") {
      const ok = confirm(
        `이 프로젝트의 현재 진행단계는 "${p.stage || "(미설정)"}" 입니다.\n` +
          `가져오면서 진행단계를 "대기"로 변경합니다. 계속하시겠습니까?`,
      );
      if (!ok) return;
      setToWaiting = true;
    }
    setBusyId(p.id);
    setAssignErr(null);
    try {
      await assignMe(p.id, { setToWaiting, forUser });
      onAssigned();
    } catch (err) {
      setAssignErr(err instanceof Error ? err.message : "추가 실패");
    } finally {
      setBusyId(null);
    }
  };

  const error = openErr ?? allErr;
  const loadingAll = searchMode && !allData;
  const loadingOpen = !searchMode && !openData;

  return (
    <Modal open={open} onClose={onClose} title="프로젝트 가져오기" size="lg">
      <div className="space-y-3">
        <p className="text-xs text-zinc-500">
          기본 목록은 본인 미담당 <b>진행중</b> 프로젝트만 보입니다. 검색어를
          입력하면 <b>전체 프로젝트(완료·종결 포함)</b>에서 찾을 수 있습니다.
        </p>

        <input
          type="search"
          placeholder="프로젝트명 또는 코드로 검색…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm outline-none focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-950"
        />

        {error && (
          <p className="rounded-md border border-red-500/40 bg-red-500/5 p-2 text-xs text-red-400">
            {error instanceof Error ? error.message : "프로젝트 로드 실패"}
          </p>
        )}
        {assignErr && (
          <p className="rounded-md border border-red-500/40 bg-red-500/5 p-2 text-xs text-red-400">
            {assignErr}
          </p>
        )}

        {loadingOpen && (
          <p className="py-8 text-center text-xs text-zinc-500">
            진행중 프로젝트 불러오는 중…
          </p>
        )}
        {loadingAll && (
          <p className="py-8 text-center text-xs text-zinc-500">
            전체 프로젝트 불러오는 중 (5~15초)…
          </p>
        )}
        {!loadingOpen && !loadingAll && candidates.length === 0 && (
          <p className="py-8 text-center text-xs text-zinc-500">
            {searchMode
              ? "검색 결과가 없습니다."
              : "가져올 수 있는 진행중 프로젝트가 없습니다."}
          </p>
        )}
        {!loadingOpen && !loadingAll && candidates.length > 0 && (
          <>
            <p className="text-[11px] text-zinc-500">
              {searchMode
                ? `검색 결과 ${candidates.length}건 (전체 ${allData?.count ?? "?"}건 중)`
                : `진행중 ${candidates.length}건 표시`}
            </p>
            <ul className="max-h-[60vh] divide-y divide-zinc-200 overflow-y-auto rounded-md border border-zinc-200 dark:divide-zinc-800 dark:border-zinc-800">
              {candidates.map((p) => {
                const isMineCompleted =
                  p.completed && p.assignees.includes(myName);
                return (
                  <li key={p.id}>
                    <button
                      type="button"
                      onClick={() => handleAssign(p)}
                      disabled={busyId === p.id}
                      className={cn(
                        "flex w-full items-center justify-between gap-3 px-3 py-2 text-left transition-colors hover:bg-zinc-50 dark:hover:bg-zinc-800/50",
                        busyId === p.id && "opacity-50",
                      )}
                    >
                      <div className="min-w-0 flex-1">
                        <p
                          className="truncate text-sm font-medium"
                          title={p.name}
                        >
                          {p.name || "(제목 없음)"}
                          {p.completed && (
                            <span className="ml-1.5 rounded bg-zinc-200 px-1.5 py-0.5 text-[10px] text-zinc-600 dark:bg-zinc-700 dark:text-zinc-300">
                              완료
                            </span>
                          )}
                        </p>
                        <p className="mt-0.5 text-[11px] text-zinc-500">
                          {p.code} · {p.stage || "—"} ·{" "}
                          {p.teams.join(", ") || "—"} ·{" "}
                          {p.assignees.length > 0
                            ? `현재 ${p.assignees.length}명 담당`
                            : "담당자 없음"}
                        </p>
                      </div>
                      <span className="shrink-0 text-xs text-zinc-500">
                        {busyId === p.id
                          ? "추가중…"
                          : isMineCompleted
                            ? "↻ 재활성화"
                            : "+ 본인 담당 추가"}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </div>
    </Modal>
  );
}
