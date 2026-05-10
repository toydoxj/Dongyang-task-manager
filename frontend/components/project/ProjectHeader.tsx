"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";

import { useAuth } from "@/components/AuthGuard";
import StageBadge from "@/components/ui/StageBadge";
import { getEmployeeTeamsMap } from "@/lib/api";
import { authFetch } from "@/lib/auth";
import type { Project } from "@/lib/domain";
import { formatDate } from "@/lib/format";

import DriveExplorerModal from "./DriveExplorerModal";
import MasterProjectModal from "./MasterProjectModal";
import ProjectStageChangeModal from "./ProjectStageChangeModal";

export default function ProjectHeader({
  project,
  actions,
}: {
  project: Project;
  /** 프로젝트 제목 옆 버튼 슬롯 (편집/날인요청 등). */
  actions?: React.ReactNode;
}) {
  const { driveLocalRoot } = useAuth();
  const [masterOpen, setMasterOpen] = useState(false);
  const [driveBusy, setDriveBusy] = useState(false);
  const [driveError, setDriveError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [explorerOpen, setExplorerOpen] = useState(false);
  const [stageChangeOpen, setStageChangeOpen] = useState(false);

  // 담당팀 — 직원 명부의 assignee.team 으로 자동 집계 (중복 제거)
  const { data: teamsMap } = useSWR(
    ["employee-teams-map"],
    () => getEmployeeTeamsMap(),
  );
  const memberTeams = useMemo(() => {
    const map = teamsMap ?? {};
    const teams = new Set<string>();
    for (const a of project.assignees) {
      const t = map[a];
      if (t) teams.add(t);
    }
    return Array.from(teams).sort((a, b) => a.localeCompare(b, "ko"));
  }, [project.assignees, teamsMap]);
  const masterLabel =
    project.master_project_name || project.master_code || "";

  // NAVER WORKS Drive 탐색기 가상 드라이브 PC 경로
  // (driveLocalRoot가 비어있으면 탐색기/복사 버튼 비표시)
  const folderName =
    project.code && project.name ? `[${project.code}]${project.name}` : "";
  const localPath =
    driveLocalRoot && folderName
      ? `${driveLocalRoot}\\${folderName}`
      : "";

  const copyLocalPath = async (): Promise<void> => {
    if (!localPath) return;
    try {
      await navigator.clipboard.writeText(localPath);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard API 차단 시 fallback — alert로 path 보여주기
      window.prompt("아래 경로를 복사하세요 (Ctrl+C):", localPath);
    }
  };

  const handleProvisionDrive = async (): Promise<void> => {
    if (driveBusy) return;
    setDriveBusy(true);
    setDriveError(null);
    try {
      const res = await authFetch(`/api/projects/${project.id}/works-drive`, {
        method: "POST",
      });
      if (!res.ok) {
        const d = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(d.detail ?? `요청 실패 (${res.status})`);
      }
      const updated = (await res.json()) as Project;
      if (updated.drive_url) {
        window.location.reload();
      } else {
        setDriveError("폴더는 생성됐지만 URL을 받지 못했습니다.");
      }
    } catch (e: unknown) {
      setDriveError(e instanceof Error ? e.message : "오류");
    } finally {
      setDriveBusy(false);
    }
  };

  return (
    <header className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-2 font-mono text-xs text-zinc-500">
            <span>{project.code || "—"}</span>
            {masterLabel && project.master_project_id && (
              <button
                type="button"
                onClick={() => setMasterOpen(true)}
                className="truncate rounded-md border border-zinc-300 px-1.5 py-0.5 text-[10px] font-sans text-zinc-700 hover:border-zinc-400 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800"
                title="마스터 프로젝트 상세"
              >
                ▣ {masterLabel}
              </button>
            )}
            {masterLabel && !project.master_project_id && (
              <span className="text-zinc-400">({masterLabel})</span>
            )}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
              {project.name || "(제목 없음)"}
            </h1>
            {actions && (
              <div className="flex items-center gap-1.5">{actions}</div>
            )}
          </div>
          <p className="mt-1 text-sm text-zinc-500">
            발주처:{" "}
            {project.client_names.length > 0
              ? project.client_names.join(", ")
              : project.client_text || "—"}
          </p>
        </div>

        <div className="flex flex-col items-end gap-2">
          {project.stage && (
            <div className="flex items-center gap-2">
              {/* 단계변경 — 모든 단계에서 노출 (완료/타절/종결 변경, 완료일 수정 등) */}
              <button
                type="button"
                onClick={() => setStageChangeOpen(true)}
                className="rounded-md border border-zinc-300 px-2.5 py-1 text-xs hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
                title="완료/타절/종결 처리"
              >
                단계변경
              </button>
              <StageBadge stage={project.stage} className="px-3 py-1 text-xs" />
            </div>
          )}
          {project.drive_url ? (
            <div className="flex flex-wrap items-center justify-end gap-1.5">
              {/* 임베디드 탐색기 모달 (앱 안에서 폴더 보기, 파일 클릭 시 NAVER 외부 탭) */}
              <button
                type="button"
                onClick={() => setExplorerOpen(true)}
                className="inline-flex items-center gap-1 rounded-md border border-amber-700/40 bg-amber-600/10 px-2.5 py-1 text-xs font-medium text-amber-300 hover:bg-amber-600/20"
                title="앱 안에서 폴더 트리 탐색"
              >
                🗂️ 폴더 보기
              </button>
              {/* WORKS Drive 웹에서 열기 */}
              <a
                href={project.drive_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 rounded-md border border-emerald-700/40 bg-emerald-600/10 px-2.5 py-1 text-xs font-medium text-emerald-300 hover:bg-emerald-600/20"
                title="WORKS Drive 웹에서 프로젝트 폴더 열기"
              >
                🌐 WORKS Drive
              </a>
              {/* PC 경로 복사 — 브라우저는 file:// 직접 클릭 차단하므로 경로 복사 → 탐색기에 붙여넣기 */}
              {localPath && (
                <button
                  type="button"
                  onClick={copyLocalPath}
                  className="inline-flex items-center gap-1 rounded-md border border-sky-700/40 bg-sky-600/10 px-2.5 py-1 text-xs font-medium text-sky-300 hover:bg-sky-600/20"
                  title={`PC 경로 복사 → 탐색기 주소창(Win+E, Ctrl+L)에 Ctrl+V → Enter\n${localPath}`}
                >
                  {copied ? "✓ 복사됨" : "📂 PC 경로 복사"}
                </button>
              )}
            </div>
          ) : (
            <button
              type="button"
              onClick={handleProvisionDrive}
              disabled={driveBusy}
              className="inline-flex items-center gap-1 rounded-md border border-zinc-300 px-2.5 py-1 text-xs text-zinc-700 hover:border-zinc-400 hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
              title="WORKS Drive 폴더 생성/연결"
            >
              {driveBusy ? "생성 중..." : "📁 Drive 폴더 만들기"}
            </button>
          )}
          {driveError && (
            <p className="text-[10px] text-red-400" title={driveError}>
              {driveError}
            </p>
          )}
        </div>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-xs md:grid-cols-4">
        <Field
          label="담당팀"
          value={
            memberTeams.length > 0
              ? memberTeams.join(", ")
              : project.teams.join(", ") || "—"
          }
        />
        <Field label="담당자" value={project.assignees.join(", ") || "—"} />
        <Field label="업무내용" value={project.work_types.join(", ") || "—"} />
        <Field label="작업단계" value={project.phase || "—"} />
        <Field label="계약" value={project.contract_signed ? "✓" : "미체결"} />
        <Field label="수주일" value={formatDate(project.start_date)} />
        <Field
          label="계약기간"
          value={
            project.contract_start
              ? `${formatDate(project.contract_start)} ~ ${formatDate(project.contract_end)}`
              : "—"
          }
        />
        <Field label="완료일" value={formatDate(project.end_date)} />
        <Field
          label="수정일"
          value={formatDate(project.last_edited_time)}
        />
      </dl>

      <MasterProjectModal
        open={masterOpen}
        pageId={project.master_project_id || null}
        onClose={() => setMasterOpen(false)}
      />

      <DriveExplorerModal
        open={explorerOpen}
        onClose={() => setExplorerOpen(false)}
        projectId={project.id}
        rootLabel={folderName || "프로젝트 폴더"}
      />

      {stageChangeOpen && (
        <ProjectStageChangeModal
          project={project}
          onClose={() => setStageChangeOpen(false)}
          onSaved={() => {
            // 변경 후 fresh data — 가장 단순하게 페이지 reload
            if (typeof window !== "undefined") window.location.reload();
          }}
        />
      )}
    </header>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-zinc-500">{label}</dt>
      <dd className="mt-0.5 truncate text-zinc-800 dark:text-zinc-200" title={value}>
        {value}
      </dd>
    </div>
  );
}
