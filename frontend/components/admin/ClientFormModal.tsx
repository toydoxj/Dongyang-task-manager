"use client";

import { useState } from "react";

import Modal from "@/components/ui/Modal";
import {
  createClient,
  deleteClient,
  updateClient,
} from "@/lib/api";
import type { Client } from "@/lib/domain";

interface Props {
  client: Client | null; // null이면 신규
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}

export default function ClientFormModal({
  client,
  open,
  onClose,
  onSaved,
}: Props) {
  if (!open) return null;
  return (
    <Form
      key={client?.id ?? "new"}
      client={client}
      onClose={onClose}
      onSaved={onSaved}
    />
  );
}

const CATEGORIES = [
  "건축사무소",
  "시공사",
  "감리",
  "발주처",
  "공공",
  "개인",
  "기타",
];

function Form({
  client,
  onClose,
  onSaved,
}: {
  client: Client | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isEdit = !!client;
  const [name, setName] = useState(client?.name ?? "");
  const [category, setCategory] = useState(client?.category ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (): Promise<void> => {
    if (!name.trim()) {
      setError("이름을 입력하세요");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (isEdit && client) {
        await updateClient(client.id, {
          name: name === client.name ? undefined : name.trim(),
          category: category === client.category ? undefined : category,
        });
      } else {
        await createClient({ name: name.trim(), category });
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "저장 실패");
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async (): Promise<void> => {
    if (!client) return;
    if (
      !confirm(
        `'${client.name}' 발주처를 삭제하시겠습니까? (노션 휴지통으로 이동, 이미 사용 중이면 거절됨)`,
      )
    )
      return;
    setBusy(true);
    setError(null);
    try {
      await deleteClient(client.id);
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "삭제 실패");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title={isEdit ? "발주처 편집" : "발주처 신규 등록"}
      size="sm"
    >
      <div className="space-y-3">
        <Field label="이름" required>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={inputCls}
            placeholder="(주)○○건축사사무소"
            autoFocus
          />
        </Field>

        <Field label="구분">
          <input
            type="text"
            list="dy-client-categories"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className={inputCls}
            placeholder="건축사무소 / 시공사 / 감리 / 기타"
          />
          <datalist id="dy-client-categories">
            {CATEGORIES.map((c) => (
              <option key={c} value={c} />
            ))}
          </datalist>
        </Field>

        {error && (
          <p className="rounded-md border border-red-500/40 bg-red-500/5 p-2 text-xs text-red-400">
            {error}
          </p>
        )}

        <footer className="flex items-center justify-between pt-2">
          {isEdit ? (
            <button
              type="button"
              onClick={onDelete}
              disabled={busy}
              className="rounded-md border border-red-500/50 px-3 py-1.5 text-xs text-red-500 hover:bg-red-500/10 disabled:opacity-50"
            >
              삭제
            </button>
          ) : (
            <span />
          )}
          <div className="flex gap-2">
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
              {busy ? "저장 중..." : isEdit ? "저장" : "등록"}
            </button>
          </div>
        </footer>
      </div>
    </Modal>
  );
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
