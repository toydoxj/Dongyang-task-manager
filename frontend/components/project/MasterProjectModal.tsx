"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { mutate } from "swr";

import {
  CheckBox,
  Input,
  NumInput,
  Tag,
  ValueRow,
} from "@/components/project/MasterProjectControls";
import Modal from "@/components/ui/Modal";
import MultiSelectChips from "@/components/ui/MultiSelectChips";
import {
  deleteMasterImage,
  updateMasterProject,
  uploadMasterImage,
} from "@/lib/api";
import type { MasterImage, MasterProject, MasterProjectUpdate } from "@/lib/domain";
import {
  masterKeys,
  useMasterImages,
  useMasterOptions,
  useMasterProject,
} from "@/lib/hooks";

interface Props {
  open: boolean;
  pageId: string | null;
  onClose: () => void;
}

export default function MasterProjectModal({ open, pageId, onClose }: Props) {
  const { data: mp, error } = useMasterProject(open ? pageId : null);
  const { data: imageData } = useMasterImages(open ? pageId : null);
  const images = imageData?.items ?? [];

  return (
    <Modal open={open} onClose={onClose} title="마스터 프로젝트" size="lg">
      {error && (
        <p className="rounded-md border border-red-500/40 bg-red-500/5 p-3 text-sm text-red-400">
          {error instanceof Error ? error.message : "로드 실패"}
        </p>
      )}

      {!mp && !error && (
        <p className="py-8 text-center text-xs text-zinc-500">불러오는 중…</p>
      )}

      {mp && pageId && (
        <Body mp={mp} pageId={pageId} images={images} onClose={onClose} />
      )}
    </Modal>
  );
}

function Body({
  mp,
  pageId,
  images,
  onClose,
}: {
  mp: MasterProject;
  pageId: string;
  images: MasterImage[];
  onClose: () => void;
}) {
  // edit 상태는 Body 내부 — 모달이 닫히면 Body unmount → 자동 리셋
  const [edit, setEdit] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleFiles(files: FileList | File[]) {
    const arr = Array.from(files).filter((f) => f.type.startsWith("image/"));
    if (arr.length === 0) return;
    setUploading(true);
    setUploadError(null);
    try {
      for (const f of arr) {
        await uploadMasterImage(pageId, f);
      }
      await mutate(masterKeys.images(pageId));
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : "업로드 실패");
    } finally {
      setUploading(false);
    }
  }

  function onPaste(e: React.ClipboardEvent) {
    const items = e.clipboardData?.items;
    if (!items) return;
    const files: File[] = [];
    for (const it of items) {
      if (it.kind === "file") {
        const f = it.getAsFile();
        if (f && f.type.startsWith("image/")) files.push(f);
      }
    }
    if (files.length > 0) {
      e.preventDefault();
      void handleFiles(files);
    }
  }

  async function handleDelete(blockId: string) {
    if (!confirm("이미지를 삭제하시겠습니까?")) return;
    try {
      await deleteMasterImage(pageId, blockId);
      await mutate(masterKeys.images(pageId));
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : "삭제 실패");
    }
  }

  return (
    <div className="space-y-5" onPaste={onPaste}>
      {edit ? (
        <EditForm
          mp={mp}
          pageId={pageId}
          onCancel={() => setEdit(false)}
          onSaved={() => setEdit(false)}
        />
      ) : (
        <ViewBlock mp={mp} onEdit={() => setEdit(true)} />
      )}

      {/* 이미지 갤러리 */}
      <section>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">
            이미지 ({images.length})
          </h3>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              className="rounded-md border border-zinc-300 bg-white px-2 py-1 text-[11px] font-medium hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
            >
              {uploading ? "업로드 중…" : "+ 이미지"}
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              multiple
              hidden
              onChange={(e) => {
                if (e.target.files) void handleFiles(e.target.files);
                e.target.value = "";
              }}
            />
          </div>
        </div>
        <p className="mb-2 text-[10px] text-zinc-500">
          이 영역에서 Ctrl+V로 클립보드 이미지 붙여넣기 가능 (≤20MB)
        </p>
        {uploadError && (
          <p className="mb-2 rounded border border-red-500/40 bg-red-500/5 p-2 text-[11px] text-red-400">
            {uploadError}
          </p>
        )}
        {images.length === 0 ? (
          <p className="rounded-md border border-dashed border-zinc-300 py-6 text-center text-[11px] text-zinc-500 dark:border-zinc-700">
            이미지 없음 — 붙여넣기 또는 + 이미지로 추가
          </p>
        ) : (
          <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {images.map((img) => (
              <li
                key={img.block_id}
                className="group relative overflow-hidden rounded-md border border-zinc-200 dark:border-zinc-800"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={img.url}
                  alt={img.caption || "이미지"}
                  className="h-32 w-full cursor-zoom-in object-cover"
                  onClick={() => window.open(img.url, "_blank", "noopener")}
                />
                <button
                  type="button"
                  onClick={() => void handleDelete(img.block_id)}
                  className="absolute right-1 top-1 hidden rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-white group-hover:block"
                  aria-label="삭제"
                >
                  ✕
                </button>
                {img.caption && (
                  <p className="bg-black/60 px-1.5 py-0.5 text-[10px] text-white">
                    {img.caption}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {mp.sub_projects.length > 0 && (
        <section>
          <h3 className="mb-2 text-xs font-semibold text-zinc-700 dark:text-zinc-300">
            Sub-Project ({mp.sub_projects.length})
          </h3>
          <ul className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
            {mp.sub_projects.map((sp) => (
              <li key={sp.id}>
                <Link
                  href={`/projects/${sp.id}`}
                  onClick={onClose}
                  className="flex items-center justify-between gap-2 rounded-md border border-zinc-200 bg-white px-2.5 py-1.5 text-[11px] hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:bg-zinc-800"
                >
                  <span className="min-w-0 flex-1 truncate">
                    <span className="font-mono text-zinc-400">
                      {sp.code || sp.id.slice(0, 8)}
                    </span>
                    {sp.name && <span className="ml-2">{sp.name}</span>}
                  </span>
                  {sp.stage && (
                    <span className="shrink-0 rounded border border-zinc-300 px-1 py-0.5 text-[9px] text-zinc-500 dark:border-zinc-700">
                      {sp.stage}
                    </span>
                  )}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {mp.url && (
        <a
          href={mp.url}
          target="_blank"
          rel="noopener noreferrer"
          className="block text-right text-xs text-zinc-500 hover:underline"
        >
          노션에서 열기 ↗
        </a>
      )}
    </div>
  );
}

function ViewBlock({
  mp,
  onEdit,
}: {
  mp: MasterProject;
  onEdit: () => void;
}) {
  return (
    <>
      <header>
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <p className="font-mono text-xs text-zinc-500">{mp.code || "—"}</p>
            <h2 className="mt-1 text-lg font-semibold">
              {mp.name || "(제목 없음)"}
            </h2>
            {mp.address && (
              <p className="mt-1 text-sm text-zinc-500">{mp.address}</p>
            )}
          </div>
          <button
            type="button"
            onClick={onEdit}
            className="shrink-0 rounded-md border border-zinc-300 bg-white px-2.5 py-1 text-[11px] font-medium hover:bg-zinc-100 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
          >
            편집
          </button>
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {mp.completed && (
            <Tag className="bg-emerald-500/15 text-emerald-400 border-emerald-500/30">
              완료
            </Tag>
          )}
          {mp.high_rise && (
            <Tag className="bg-orange-500/15 text-orange-400 border-orange-500/30">
              고층
            </Tag>
          )}
          {mp.multi_use && (
            <Tag className="bg-purple-500/15 text-purple-400 border-purple-500/30">
              다중이용시설
            </Tag>
          )}
          {mp.special_structure && (
            <Tag className="bg-pink-500/15 text-pink-400 border-pink-500/30">
              특수구조
            </Tag>
          )}
          {mp.special_types.map((t) => (
            <Tag
              key={t}
              className="bg-yellow-500/15 text-yellow-500 border-yellow-500/30"
            >
              {t}
            </Tag>
          ))}
        </div>
      </header>

      <section>
        <h3 className="mb-2 text-xs font-semibold text-zinc-700 dark:text-zinc-300">
          건축 정보
        </h3>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs md:grid-cols-3">
          <ValueRow label="용도" value={mp.usage.join(", ")} />
          <ValueRow label="구조형식" value={mp.structure.join(", ")} />
          <ValueRow
            label="규모"
            value={
              [
                mp.units != null ? `${mp.units}동` : "",
                mp.floors_above != null ? `지상 ${mp.floors_above}층` : "",
                mp.floors_below != null ? `지하 ${mp.floors_below}층` : "",
              ]
                .filter(Boolean)
                .join(" / ") || "—"
            }
          />
          <ValueRow
            label="높이"
            value={mp.height != null ? `${mp.height} m` : "—"}
          />
          <ValueRow
            label="연면적"
            value={
              mp.area != null
                ? `${mp.area.toLocaleString("ko-KR")} m²`
                : "—"
            }
          />
        </dl>
      </section>
    </>
  );
}

function EditForm({
  mp,
  pageId,
  onCancel,
  onSaved,
}: {
  mp: MasterProject;
  pageId: string;
  onCancel: () => void;
  onSaved: () => void;
}) {
  const { data: options } = useMasterOptions();
  const [form, setForm] = useState<MasterProjectUpdate>({
    name: mp.name,
    code: mp.code,
    address: mp.address,
    usage: mp.usage,
    structure: mp.structure,
    floors_above: mp.floors_above,
    floors_below: mp.floors_below,
    height: mp.height,
    area: mp.area,
    units: mp.units,
    high_rise: mp.high_rise,
    multi_use: mp.multi_use,
    special_structure: mp.special_structure,
    completed: mp.completed,
    special_types: mp.special_types,
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  function setField<K extends keyof MasterProjectUpdate>(
    key: K,
    value: MasterProjectUpdate[K],
  ) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function onSave() {
    setSaving(true);
    setErr(null);
    try {
      const updated = await updateMasterProject(pageId, form);
      // SWR 캐시 갱신
      await mutate(masterKeys.master(pageId), updated, { revalidate: false });
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "저장 실패");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="space-y-3">
      {err && (
        <p className="rounded-md border border-red-500/40 bg-red-500/5 p-2 text-xs text-red-400">
          {err}
        </p>
      )}
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <Input
          label="용역명"
          value={form.name ?? ""}
          onChange={(v) => setField("name", v)}
          full
        />
        <Input
          label="MASTER_CODE"
          value={form.code ?? ""}
          onChange={(v) => setField("code", v)}
        />
        <Input
          label="주소"
          value={form.address ?? ""}
          onChange={(v) => setField("address", v)}
          full
        />
        <MultiSelectChips
          label="용도"
          value={form.usage ?? []}
          options={options?.usage ?? []}
          onChange={(v) => setField("usage", v)}
        />
        <MultiSelectChips
          label="구조형식"
          value={form.structure ?? []}
          options={options?.structure ?? []}
          onChange={(v) => setField("structure", v)}
        />
        <MultiSelectChips
          label="특수유형"
          value={form.special_types ?? []}
          options={options?.special_types ?? []}
          onChange={(v) => setField("special_types", v)}
          full
        />
        <NumInput
          label="동수"
          value={form.units ?? null}
          onChange={(v) => setField("units", v)}
        />
        <NumInput
          label="지상층수"
          value={form.floors_above ?? null}
          onChange={(v) => setField("floors_above", v)}
        />
        <NumInput
          label="지하층수"
          value={form.floors_below ?? null}
          onChange={(v) => setField("floors_below", v)}
        />
        <NumInput
          label="높이 (m)"
          value={form.height ?? null}
          onChange={(v) => setField("height", v)}
        />
        <NumInput
          label="연면적 (m²)"
          value={form.area ?? null}
          onChange={(v) => setField("area", v)}
        />
      </div>
      <div className="flex flex-wrap gap-3 text-xs">
        <CheckBox
          label="고층건축물"
          value={!!form.high_rise}
          onChange={(v) => setField("high_rise", v)}
        />
        <CheckBox
          label="다중이용시설"
          value={!!form.multi_use}
          onChange={(v) => setField("multi_use", v)}
        />
        <CheckBox
          label="특수구조"
          value={!!form.special_structure}
          onChange={(v) => setField("special_structure", v)}
        />
        <CheckBox
          label="완료"
          value={!!form.completed}
          onChange={(v) => setField("completed", v)}
        />
      </div>
      <div className="flex justify-end gap-2 pt-1">
        <button
          type="button"
          onClick={onCancel}
          disabled={saving}
          className="rounded-md border border-zinc-300 bg-white px-3 py-1 text-xs hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800"
        >
          취소
        </button>
        <button
          type="button"
          onClick={() => void onSave()}
          disabled={saving}
          className="rounded-md bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {saving ? "저장 중…" : "저장"}
        </button>
      </div>
    </section>
  );
}

