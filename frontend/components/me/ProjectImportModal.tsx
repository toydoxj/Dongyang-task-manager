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
}

export default function ProjectImportModal({
  open,
  onClose,
  onAssigned,
  myName,
}: Props) {
  // 모달 열릴 때 전체 진행중 프로젝트 fetch (캐시 활용)
  const { data, error } = useProjects(open ? { stage: "진행중" } : undefined);
  const [query, setQuery] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [assignErr, setAssignErr] = useState<string | null>(null);

  const candidates = useMemo<Project[]>(() => {
    if (!data) return [];
    const q = query.trim().toLowerCase();
    return data.items
      .filter((p) => !p.completed && !p.assignees.includes(myName))
      .filter((p) => {
        if (!q) return true;
        return `${p.code} ${p.name}`.toLowerCase().includes(q);
      })
      .slice(0, 50);
  }, [data, query, myName]);

  const handleAssign = async (p: Project): Promise<void> => {
    setBusyId(p.id);
    setAssignErr(null);
    try {
      await assignMe(p.id);
      onAssigned();
    } catch (err) {
      setAssignErr(err instanceof Error ? err.message : "추가 실패");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="프로젝트 가져오기" size="lg">
      <div className="space-y-3">
        <p className="text-xs text-zinc-500">
          현재 본인이 담당으로 등록되지 않은 진행중 프로젝트입니다. 클릭하면
          본인을 담당자에 추가합니다.
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

        {!data ? (
          <p className="py-8 text-center text-xs text-zinc-500">
            전체 프로젝트 불러오는 중…
          </p>
        ) : candidates.length === 0 ? (
          <p className="py-8 text-center text-xs text-zinc-500">
            가져올 수 있는 진행중 프로젝트가 없습니다.
          </p>
        ) : (
          <ul className="max-h-[60vh] divide-y divide-zinc-200 overflow-y-auto rounded-md border border-zinc-200 dark:divide-zinc-800 dark:border-zinc-800">
            {candidates.map((p) => (
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
                    <p className="truncate text-sm font-medium" title={p.name}>
                      {p.name || "(제목 없음)"}
                    </p>
                    <p className="mt-0.5 text-[11px] text-zinc-500">
                      {p.code} · {p.teams.join(", ") || "—"} ·{" "}
                      {p.assignees.length > 0
                        ? `현재 ${p.assignees.length}명 담당`
                        : "담당자 없음"}
                    </p>
                  </div>
                  <span className="shrink-0 text-xs text-zinc-500">
                    {busyId === p.id ? "추가중…" : "+ 본인 담당 추가"}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Modal>
  );
}
