"use client";

import { useState } from "react";

import { useAuth } from "@/components/AuthGuard";
import { authFetch } from "@/lib/auth";
import type { Project } from "@/lib/domain";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

import MasterProjectModal from "./MasterProjectModal";

const STAGE_BADGE: Record<string, string> = {
  "진행중": "bg-blue-500/15 text-blue-400 border-blue-500/30",
  "대기": "bg-purple-500/15 text-purple-400 border-purple-500/30",
  "보류": "bg-pink-500/15 text-pink-400 border-pink-500/30",
  "완료": "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  "타절": "bg-red-500/15 text-red-400 border-red-500/30",
  "종결": "bg-zinc-500/15 text-zinc-400 border-zinc-500/30",
  "이관": "bg-zinc-400/15 text-zinc-400 border-zinc-400/30",
};

export default function ProjectHeader({ project }: { project: Project }) {
  const { user } = useAuth();
  const [masterOpen, setMasterOpen] = useState(false);
  const [driveBusy, setDriveBusy] = useState(false);
  const [driveError, setDriveError] = useState<string | null>(null);
  const masterLabel =
    project.master_project_name || project.master_code || "";

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
          <h1 className="mt-1 text-xl font-semibold text-zinc-900 dark:text-zinc-100">
            {project.name || "(제목 없음)"}
          </h1>
          <p className="mt-1 text-sm text-zinc-500">
            발주처:{" "}
            {project.client_names.length > 0
              ? project.client_names.join(", ")
              : project.client_text || "—"}
          </p>
        </div>

        <div className="flex flex-col items-end gap-2">
          {project.stage && (
            <span
              className={cn(
                "rounded-md border px-3 py-1 text-xs font-medium",
                STAGE_BADGE[project.stage] ??
                  "border-zinc-500/30 bg-zinc-500/15 text-zinc-400",
              )}
            >
              {project.stage}
            </span>
          )}
          {project.drive_url ? (
            <a
              href={project.drive_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 rounded-md border border-emerald-700/40 bg-emerald-600/10 px-2.5 py-1 text-xs font-medium text-emerald-300 hover:bg-emerald-600/20"
              title="WORKS Drive에서 프로젝트 폴더 열기"
            >
              📁 WORKS Drive 열기
            </a>
          ) : user?.role === "admin" ? (
            <button
              type="button"
              onClick={handleProvisionDrive}
              disabled={driveBusy}
              className="inline-flex items-center gap-1 rounded-md border border-zinc-300 px-2.5 py-1 text-xs text-zinc-700 hover:border-zinc-400 hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
              title="WORKS Drive 폴더 생성/연결"
            >
              {driveBusy ? "생성 중..." : "📁 Drive 폴더 만들기"}
            </button>
          ) : null}
          {driveError && (
            <p className="text-[10px] text-red-400" title={driveError}>
              {driveError}
            </p>
          )}
        </div>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-xs md:grid-cols-4">
        <Field label="담당팀" value={project.teams.join(", ") || "—"} />
        <Field label="담당자" value={project.assignees.join(", ") || "—"} />
        <Field label="업무내용" value={project.work_types.join(", ") || "—"} />
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
