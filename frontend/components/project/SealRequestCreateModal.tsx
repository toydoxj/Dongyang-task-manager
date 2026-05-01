"use client";

import { useMemo, useState } from "react";
import useSWR, { useSWRConfig } from "swr";

import { useAuth } from "@/components/AuthGuard";
import DriveExplorerModal from "@/components/project/DriveExplorerModal";
import Modal from "@/components/ui/Modal";
import {
  createReviewFolder,
  createSealRequest,
  getNextSealDocNumber,
  getReviewFolder,
} from "@/lib/api";
import type { Project } from "@/lib/domain";
import { useClients, useProjects } from "@/lib/hooks";

const SEAL_TYPES = [
  "구조계산서",
  "구조안전확인서",
  "구조검토서",
  "구조도면",
  "보고서",
  "기타",
] as const;
type SealType = (typeof SEAL_TYPES)[number];

interface Props {
  open: boolean;
  /** 프로젝트 컨텍스트 고정 (프로젝트 상세에서 호출 시). */
  fixedProject?: Project | null;
  onClose: () => void;
  onCreated: () => void;
}

export default function SealRequestCreateModal({
  open,
  fixedProject,
  onClose,
  onCreated,
}: Props) {
  if (!open) return null;
  return (
    <Form
      key={fixedProject?.id ?? "new"}
      fixedProject={fixedProject}
      onClose={onClose}
      onCreated={onCreated}
    />
  );
}

function Form({
  fixedProject,
  onClose,
  onCreated,
}: {
  fixedProject?: Project | null;
  onClose: () => void;
  onCreated: () => void;
}) {
  const { user } = useAuth();
  const { data: projectData } = useProjects(
    !fixedProject && user?.name ? { mine: true } : undefined,
    !fixedProject,
  );
  const myProjects = projectData?.items ?? [];
  const { data: clientData } = useClients(true);
  const clients = clientData?.items ?? [];

  const [projectId, setProjectId] = useState(fixedProject?.id ?? "");
  const [sealType, setSealType] = useState<SealType>("구조계산서");
  const [title, setTitle] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [note, setNote] = useState("");
  // 조건부 필드
  // 실제출처는 거래처명 입력 → datalist 매칭 시 client.id로 변환해 server에 전송
  const [realSourceName, setRealSourceName] = useState("");
  const [purpose, setPurpose] = useState("");
  const [revision, setRevision] = useState(0);
  const [withSafetyCert, setWithSafetyCert] = useState(false);
  const [summary, setSummary] = useState("");
  const [docKind, setDocKind] = useState("");

  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // 구조검토서 다음 문서번호 미리보기 — 모달 열린 동안 1회 fetch (1분 dedupe)
  const { data: nextDocData } = useSWR(
    sealType === "구조검토서" ? ["seal-next-doc", sealType] : null,
    () => getNextSealDocNumber(sealType),
    { dedupingInterval: 60 * 1000 },
  );
  const nextDocNumber = nextDocData?.next_doc_number ?? "";

  // 검토자료 폴더 상태 — 프로젝트 결정 시 fetch
  const { mutate: globalMutate } = useSWRConfig();
  const folderKey = projectId ? ["review-folder", projectId] : null;
  const { data: folderState } = useSWR(folderKey, () =>
    getReviewFolder(projectId),
  );
  const [folderBusy, setFolderBusy] = useState(false);
  const [explorerOpen, setExplorerOpen] = useState(false);

  const handleCreateFolder = async (): Promise<void> => {
    if (!projectId) return;
    setFolderBusy(true);
    try {
      const result = await createReviewFolder(projectId);
      await globalMutate(folderKey, result, { revalidate: false });
    } catch (e) {
      setErr(e instanceof Error ? e.message : "폴더 생성 실패");
    } finally {
      setFolderBusy(false);
    }
  };

  const selectedProject = useMemo<Project | null>(() => {
    if (fixedProject) return fixedProject;
    return myProjects.find((p) => p.id === projectId) ?? null;
  }, [fixedProject, myProjects, projectId]);

  // 프로젝트의 발주처 — relation 매칭 우선, 못 찾으면 client_text(임시) fallback
  const projectClientLabel = useMemo<string>(() => {
    if (!selectedProject) return "";
    const ids = selectedProject.client_relation_ids ?? [];
    const names = ids
      .map((id) => clients.find((c) => c.id === id)?.name)
      .filter((n): n is string => !!n);
    if (names.length > 0) return names.join(", ");
    return selectedProject.client_text ?? "";
  }, [selectedProject, clients]);

  const titlePreview = useMemo(() => {
    if (title.trim()) return title.trim();
    const code = (selectedProject?.code || "?").trim();
    switch (sealType) {
      case "구조계산서":
        return `${code}_구조계산서_rev${revision || 0}_${purpose || "?"}`;
      case "구조안전확인서":
        return `${code}_구조안전확인서_${purpose || "?"}`;
      case "구조검토서":
        return `${code}_${nextDocNumber || "(자동발급)"}_구조검토서`;
      case "구조도면":
        return `${code}_구조도면_${purpose || "?"}`;
      case "보고서":
        return `${code}_보고서`;
      case "기타":
        return `${code}_${docKind || "기타"}`;
    }
  }, [title, selectedProject, sealType, revision, purpose, docKind, nextDocNumber]);

  const submit = async (): Promise<void> => {
    if (!projectId) {
      setErr("프로젝트를 선택하세요");
      return;
    }
    if (!dueDate) {
      setErr("제출 예정일은 필수입니다");
      return;
    }
    if (sealType === "구조계산서" && !purpose.trim()) {
      setErr("구조계산서: 용도를 입력하세요");
      return;
    }
    if (sealType === "구조안전확인서" && !purpose.trim()) {
      setErr("구조안전확인서: 용도를 입력하세요");
      return;
    }
    if (sealType === "구조도면" && !purpose.trim()) {
      setErr("구조도면: 용도를 입력하세요");
      return;
    }
    if (sealType === "기타" && !docKind.trim()) {
      setErr("기타: 문서종류를 입력하세요");
      return;
    }
    // 검토자료 폴더 경고 — 폴더 없거나 비어있으면 사용자 확인
    if (!folderState?.exists) {
      const ok = window.confirm(
        "검토자료 폴더가 생성되지 않았습니다.\n그대로 등록하시겠습니까?",
      );
      if (!ok) return;
    } else if (folderState.file_count === 0) {
      const ok = window.confirm(
        "검토자료 폴더가 비어있습니다 (파일 0개).\n그대로 등록하시겠습니까?",
      );
      if (!ok) return;
    }
    setBusy(true);
    setErr(null);
    try {
      const fd = new FormData();
      fd.append("project_id", projectId);
      fd.append("seal_type", sealType);
      fd.append("title", title);
      fd.append("due_date", dueDate);
      fd.append("note", note);
      // 거래처명 → 매칭되는 page_id로 변환. 매칭 실패 시 ""(현재는 무시).
      // 거래처 자동 추가 흐름은 후속 작업에서 통합 처리.
      const matchedClient = clients.find(
        (c) => c.name.trim() === realSourceName.trim(),
      );
      fd.append("real_source_id", matchedClient?.id ?? "");
      fd.append("purpose", purpose);
      fd.append("revision", String(revision || 0));
      fd.append("with_safety_cert", withSafetyCert ? "true" : "false");
      fd.append("summary", summary);
      fd.append("doc_kind", docKind);
      // 첨부 input은 폐지 — files 미첨부. 폴더만 자동 생성됨.
      await createSealRequest(fd);
      onCreated();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "등록 실패");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open onClose={onClose} title="새 날인요청" size="md">
      <div className="space-y-3">
        <Field label="프로젝트" required>
          {fixedProject ? (
            <p className="rounded-md border border-zinc-200 bg-zinc-50 px-2.5 py-1.5 text-sm dark:border-zinc-800 dark:bg-zinc-900">
              {fixedProject.code ? `[${fixedProject.code}] ` : ""}
              {fixedProject.name}
            </p>
          ) : (
            <select
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
              className={inputCls}
            >
              <option value="">— 선택하세요</option>
              {myProjects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.code ? `[${p.code}] ` : ""}
                  {p.name}
                </option>
              ))}
            </select>
          )}
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="검토구분" required>
            <select
              value={sealType}
              onChange={(e) => setSealType(e.target.value as SealType)}
              className={inputCls}
            >
              {SEAL_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </Field>
          <Field label="제출 예정일" required>
            <input
              type="date"
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
              className={inputCls}
            />
          </Field>
        </div>

        <Field label="실제출처 (발주처와 다른 경우만)">
          {projectClientLabel && (
            <p className="mb-1 text-[11px] text-zinc-500">
              프로젝트 발주처: <span className="font-medium">{projectClientLabel}</span>
            </p>
          )}
          <input
            type="text"
            list="dy-clients-seal-create"
            value={realSourceName}
            onChange={(e) => setRealSourceName(e.target.value)}
            placeholder="거래처 검색 — 비워두면 위 발주처 사용"
            className={inputCls}
          />
          <datalist id="dy-clients-seal-create">
            {clients.map((c) => (
              <option key={c.id} value={c.name}>
                {c.category}
              </option>
            ))}
          </datalist>
        </Field>

        {/* 검토구분별 조건부 필드 */}
        {sealType === "구조계산서" && (
          <div className="grid grid-cols-3 gap-3 rounded-md border border-zinc-200 p-2 dark:border-zinc-800">
            <Field label="Revision">
              <input
                type="number"
                value={revision}
                min={0}
                onChange={(e) => setRevision(Number(e.target.value) || 0)}
                className={inputCls}
              />
            </Field>
            <Field label="용도" required>
              <input
                type="text"
                value={purpose}
                onChange={(e) => setPurpose(e.target.value)}
                placeholder="예: 허가용 / 실시설계 / 착공용"
                className={inputCls}
              />
            </Field>
            <label className="mt-5 flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={withSafetyCert}
                onChange={(e) => setWithSafetyCert(e.target.checked)}
              />
              구조안전확인서 포함
            </label>
          </div>
        )}

        {sealType === "구조안전확인서" && (
          <Field label="용도" required>
            <input
              type="text"
              value={purpose}
              onChange={(e) => setPurpose(e.target.value)}
              placeholder="예: 허가용 / 실시설계 / 착공용"
              className={inputCls}
            />
          </Field>
        )}

        {sealType === "구조검토서" && (
          <>
            <Field label="문서번호 (자동 발급)">
              <p className="rounded-md border border-zinc-200 bg-zinc-50 px-2.5 py-1.5 text-sm font-mono dark:border-zinc-800 dark:bg-zinc-900">
                {nextDocNumber || "불러오는 중..."}
              </p>
              <p className="mt-0.5 text-[10px] text-zinc-400">
                등록 시점에 다시 발급되므로 이 번호와 다를 수 있습니다.
              </p>
            </Field>
            <Field label="내용요약">
              <textarea
                value={summary}
                onChange={(e) => setSummary(e.target.value)}
                rows={3}
                placeholder="검토 의견 요약"
                className={`${inputCls} resize-y`}
              />
            </Field>
          </>
        )}

        {sealType === "구조도면" && (
          <Field label="용도" required>
            <input
              type="text"
              value={purpose}
              onChange={(e) => setPurpose(e.target.value)}
              placeholder="예: 허가용 / 실시설계 / 착공용"
              className={inputCls}
            />
          </Field>
        )}

        {sealType === "기타" && (
          <Field label="문서종류" required>
            <input
              type="text"
              value={docKind}
              onChange={(e) => setDocKind(e.target.value)}
              placeholder="예: 공사관리계획"
              className={inputCls}
            />
          </Field>
        )}

        <Field label="제목 (생략 시 자동 생성)">
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={titlePreview}
            className={inputCls}
          />
          <p className="mt-0.5 text-[10px] text-zinc-400">
            미리보기: <span className="font-mono">{titlePreview}</span>
          </p>
        </Field>

        <Field label="비고">
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={2}
            className={`${inputCls} resize-y`}
          />
        </Field>

        <Field label="검토자료 폴더">
          {!projectId ? (
            <p className="text-[11px] text-zinc-400">
              프로젝트를 먼저 선택하세요.
            </p>
          ) : !folderState ? (
            <p className="text-[11px] text-zinc-400">폴더 상태 확인 중...</p>
          ) : folderState.exists ? (
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => setExplorerOpen(true)}
                className="inline-flex items-center gap-1 rounded-md border border-emerald-700/40 bg-emerald-600/10 px-2.5 py-1 text-xs font-medium text-emerald-700 hover:bg-emerald-600/20 dark:text-emerald-300"
              >
                📁 폴더 열기
              </button>
              <span className="text-[11px] text-zinc-500">
                파일 {folderState.file_count}개{" "}
                {folderState.file_count === 0 && "(비어있음 — 업로드 후 등록 권장)"}
              </span>
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={handleCreateFolder}
                disabled={folderBusy}
                className="inline-flex items-center gap-1 rounded-md border border-amber-700/40 bg-amber-600/10 px-2.5 py-1 text-xs font-medium text-amber-700 hover:bg-amber-600/20 disabled:opacity-50 dark:text-amber-300"
              >
                {folderBusy ? "생성 중..." : "📁 폴더 생성"}
              </button>
              <span className="text-[11px] text-zinc-500">
                <span className="font-mono">0.검토자료/{getTodayYmd()}/</span>{" "}
                — 클릭 시 즉시 생성
              </span>
            </div>
          )}
        </Field>

        {err && (
          <p className="rounded-md border border-red-500/40 bg-red-500/5 p-2 text-xs text-red-400">
            {err}
          </p>
        )}

        <footer className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
          >
            취소
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={busy}
            className="rounded-md bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
          >
            {busy ? "등록 중..." : "등록"}
          </button>
        </footer>
      </div>

      {selectedProject && folderState?.folder_id && (
        <DriveExplorerModal
          open={explorerOpen}
          onClose={() => {
            setExplorerOpen(false);
            // 탐색기에서 업로드/삭제했을 수 있으니 file_count 즉시 갱신
            void globalMutate(folderKey);
          }}
          projectId={selectedProject.id}
          rootLabel={
            selectedProject.code && selectedProject.name
              ? `[${selectedProject.code}]${selectedProject.name}`
              : selectedProject.name || "프로젝트 폴더"
          }
          initialFolderId={folderState.folder_id}
          initialFolderLabel={`0.검토자료/${folderState.ymd}`}
        />
      )}
    </Modal>
  );
}

function getTodayYmd(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}${m}${day}`;
}

const inputCls =
  "w-full rounded-md border border-zinc-300 bg-white px-2.5 py-1.5 text-sm outline-none focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-950";

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-zinc-500">
        {label}
        {required && <span className="ml-1 text-red-500">*</span>}
      </span>
      {children}
    </label>
  );
}
