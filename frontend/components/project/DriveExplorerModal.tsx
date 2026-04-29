"use client";

import { useEffect, useState } from "react";

import Modal from "@/components/ui/Modal";
import { listDriveChildren } from "@/lib/api";
import type { DriveFileType, DriveItem } from "@/lib/domain";

interface Props {
  open: boolean;
  onClose: () => void;
  projectId: string;
  rootLabel: string; // 예: "[26-001]프로젝트명"
}

interface BreadcrumbEntry {
  fileId: string | null; // null = 프로젝트 root
  name: string;
}

const TYPE_ICON: Record<DriveFileType, string> = {
  FOLDER: "📁",
  DOC: "📄",
  IMAGE: "🖼️",
  VIDEO: "🎥",
  AUDIO: "🎵",
  ZIP: "📦",
  EXE: "⚙️",
  ETC: "📎",
};

function formatSize(bytes: number): string {
  if (!bytes) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = bytes;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v >= 100 ? 0 : 1)} ${units[i]}`;
}

function formatDate(iso: string): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("ko-KR", {
      year: "2-digit",
      month: "2-digit",
      day: "2-digit",
    });
  } catch {
    return iso;
  }
}

function compare(a: DriveItem, b: DriveItem): number {
  // 폴더 먼저, 그 안에서 fileName asc
  if (a.fileType === "FOLDER" && b.fileType !== "FOLDER") return -1;
  if (a.fileType !== "FOLDER" && b.fileType === "FOLDER") return 1;
  return a.fileName.localeCompare(b.fileName, "ko");
}

export default function DriveExplorerModal({
  open,
  onClose,
  projectId,
  rootLabel,
}: Props) {
  const [stack, setStack] = useState<BreadcrumbEntry[]>([
    { fileId: null, name: rootLabel || "루트" },
  ]);
  const [items, setItems] = useState<DriveItem[]>([]);
  const [cursor, setCursor] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const current = stack[stack.length - 1];

  const load = async (
    folderId: string | null,
    nextCursor: string | undefined,
    append: boolean,
  ): Promise<void> => {
    if (append) setLoadingMore(true);
    else setLoading(true);
    setError(null);
    try {
      const res = await listDriveChildren(
        projectId,
        folderId ?? undefined,
        nextCursor || undefined,
      );
      const sorted = [...res.items].sort(compare);
      setItems(append ? [...items, ...sorted] : sorted);
      setCursor(res.next_cursor || "");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "로드 실패");
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  };

  useEffect(() => {
    if (!open) return;
    setStack([{ fileId: null, name: rootLabel || "루트" }]);
    void load(null, undefined, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, projectId]);

  const enterFolder = (it: DriveItem): void => {
    setStack([...stack, { fileId: it.fileId, name: it.fileName }]);
    void load(it.fileId, undefined, false);
  };

  const goBreadcrumb = (idx: number): void => {
    if (idx === stack.length - 1) return;
    const newStack = stack.slice(0, idx + 1);
    setStack(newStack);
    const target = newStack[newStack.length - 1];
    void load(target.fileId, undefined, false);
  };

  const onItemClick = (it: DriveItem): void => {
    if (it.fileType === "FOLDER") {
      enterFolder(it);
    } else if (it.webUrl) {
      window.open(it.webUrl, "_blank", "noopener,noreferrer");
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="🗂️ 프로젝트 폴더" size="lg">
      {/* breadcrumb */}
      <nav className="mb-3 flex flex-wrap items-center gap-1 text-xs">
        {stack.map((entry, idx) => (
          <span key={`${entry.fileId ?? "root"}-${idx}`} className="flex items-center gap-1">
            {idx > 0 && <span className="text-zinc-400">/</span>}
            <button
              type="button"
              onClick={() => goBreadcrumb(idx)}
              disabled={idx === stack.length - 1}
              className={
                idx === stack.length - 1
                  ? "font-medium text-zinc-900 dark:text-zinc-100"
                  : "text-zinc-500 hover:text-zinc-900 hover:underline dark:hover:text-zinc-100"
              }
              title={entry.name}
            >
              {idx === 0 ? "📁 " : ""}
              {entry.name}
            </button>
          </span>
        ))}
      </nav>

      {error && (
        <p className="mb-3 rounded-md border border-red-700/40 bg-red-500/5 p-2 text-xs text-red-400">
          {error}
        </p>
      )}

      {/* file/folder list */}
      <div className="overflow-hidden rounded-md border border-zinc-200 dark:border-zinc-800">
        {loading ? (
          <p className="p-6 text-center text-xs text-zinc-500">로딩 중...</p>
        ) : items.length === 0 ? (
          <p className="p-6 text-center text-xs text-zinc-500">
            이 폴더는 비어있습니다.
          </p>
        ) : (
          <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
            {items.map((it) => (
              <li key={it.fileId}>
                <button
                  type="button"
                  onClick={() => onItemClick(it)}
                  className="flex w-full items-center gap-3 px-3 py-2 text-left text-xs hover:bg-zinc-50 dark:hover:bg-zinc-800"
                >
                  <span className="w-5 text-base leading-none">
                    {TYPE_ICON[it.fileType] ?? "📎"}
                  </span>
                  <span className="flex-1 truncate text-zinc-900 dark:text-zinc-100">
                    {it.fileName}
                    {it.fileType !== "FOLDER" && (
                      <span className="ml-1 text-zinc-400">↗</span>
                    )}
                  </span>
                  <span className="w-20 text-right text-zinc-500">
                    {it.fileType === "FOLDER" ? "—" : formatSize(it.fileSize)}
                  </span>
                  <span className="w-20 text-right text-zinc-500">
                    {formatDate(it.modifiedTime)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* footer: 더 보기 + 카운트 */}
      <div className="mt-3 flex items-center justify-between text-xs text-zinc-500">
        <span>{loading ? "" : `${items.length}건${cursor ? "+" : ""}`}</span>
        {cursor && (
          <button
            type="button"
            onClick={() => void load(current.fileId, cursor, true)}
            disabled={loadingMore}
            className="rounded-md border border-zinc-300 px-3 py-1 text-zinc-700 hover:border-zinc-400 hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
          >
            {loadingMore ? "로드 중..." : "더 보기"}
          </button>
        )}
      </div>
    </Modal>
  );
}
