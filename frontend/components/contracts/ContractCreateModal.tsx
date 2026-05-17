"use client";

/**
 * 계약서 신규 생성 모달 — PR-FH/2 / PR-FI/2 (프로젝트 검색 typeahead).
 * 프로젝트 선택 + 메타 입력. 파일 업로드는 생성 후 상세 drawer에서 별도 수행.
 */

import { useMemo, useState } from "react";

import { Field, inputCls } from "@/components/project/_shared";
import Modal from "@/components/ui/Modal";
import { createContract } from "@/lib/api";
import type { Project } from "@/lib/domain";
import { cn } from "@/lib/utils";

interface Props {
  open: boolean;
  projects: Project[];
  onClose: () => void;
  onCreated: () => void;
}

export default function ContractCreateModal({
  open,
  projects,
  onClose,
  onCreated,
}: Props) {
  const [projectId, setProjectId] = useState("");
  const [title, setTitle] = useState("원계약서");
  const [signedDate, setSignedDate] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [amount, setAmount] = useState<string>("");
  const [vatIncluded, setVatIncluded] = useState(false);
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = (): void => {
    setProjectId("");
    setTitle("원계약서");
    setSignedDate("");
    setStartDate("");
    setEndDate("");
    setAmount("");
    setVatIncluded(false);
    setNote("");
    setError(null);
  };

  const handleClose = (): void => {
    if (submitting) return;
    reset();
    onClose();
  };

  const handleSubmit = async (e: React.FormEvent): Promise<void> => {
    e.preventDefault();
    if (!projectId) {
      setError("프로젝트를 선택해주세요");
      return;
    }
    if (!title.trim()) {
      setError("계약서명을 입력해주세요");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await createContract({
        project_id: projectId,
        title: title.trim(),
        signed_date: signedDate || null,
        start_date: startDate || null,
        end_date: endDate || null,
        amount: amount ? parseInt(amount, 10) : null,
        vat_included: vatIncluded,
        note: note.trim(),
      });
      reset();
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal open={open} onClose={handleClose} title="새 계약서 등록" size="lg">
      <form onSubmit={handleSubmit} className="space-y-3">
        <Field label="프로젝트" required>
          <ProjectSearchSelect
            projects={projects}
            value={projectId}
            onChange={setProjectId}
          />
        </Field>
        <Field label="계약서명" required>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="예: 원계약서, 1차 변경계약서"
            className={inputCls}
          />
        </Field>
        <div className="grid grid-cols-3 gap-3">
          <Field label="체결일">
            <input
              type="date"
              value={signedDate}
              onChange={(e) => setSignedDate(e.target.value)}
              className={inputCls}
            />
          </Field>
          <Field label="계약 시작일">
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className={inputCls}
            />
          </Field>
          <Field label="계약 종료일">
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className={inputCls}
            />
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="계약금액 (원)">
            <input
              type="number"
              min={0}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="50000000"
              className={inputCls}
            />
          </Field>
          <label className="flex items-end gap-2 pb-1.5">
            <input
              type="checkbox"
              checked={vatIncluded}
              onChange={(e) => setVatIncluded(e.target.checked)}
            />
            <span className="text-xs text-zinc-700 dark:text-zinc-300">
              VAT 포함 금액
            </span>
          </label>
        </div>
        <Field label="메모">
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={2}
            className={inputCls}
          />
        </Field>
        {error && (
          <p className="rounded-md border border-red-500/40 bg-red-500/5 px-3 py-2 text-xs text-red-500">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={handleClose}
            disabled={submitting}
            className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
          >
            취소
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
          >
            {submitting ? "등록 중…" : "등록"}
          </button>
        </div>
        <p className="text-[10px] text-zinc-500">
          PDF 파일은 등록 후 상세에서 업로드합니다.
        </p>
      </form>
    </Modal>
  );
}

/** PR-FI/2: 프로젝트 검색 typeahead — 운영 N=수백 대응. */
function ProjectSearchSelect({
  projects,
  value,
  onChange,
}: {
  projects: Project[];
  value: string;
  onChange: (id: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [focused, setFocused] = useState(false);

  const selected = useMemo(
    () => (value ? projects.find((p) => p.id === value) : null),
    [value, projects],
  );

  // 선택된 프로젝트가 있으면 input에는 그 표시. 사용자가 다시 검색하려면 X(clear) 클릭.
  const display = selected
    ? `${selected.code ? `[${selected.code}] ` : ""}${selected.name || "(이름 없음)"}`
    : query;

  // 결과 필터 — CODE / 이름 부분일치 (case-insensitive). 결과 ≤ 30개.
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return projects.slice(0, 30);
    return projects
      .filter((p) => {
        const haystack = `${p.code ?? ""} ${p.name ?? ""}`.toLowerCase();
        return haystack.includes(q);
      })
      .slice(0, 30);
  }, [projects, query]);

  const handleClear = (): void => {
    onChange("");
    setQuery("");
  };

  const handleSelect = (p: Project): void => {
    onChange(p.id);
    setQuery("");
    setFocused(false);
  };

  return (
    <div className="relative">
      <div className="relative">
        <input
          type="text"
          value={display}
          onChange={(e) => {
            // 입력 시 기존 선택 해제 (사용자가 검색을 새로 함)
            if (selected) onChange("");
            setQuery(e.target.value);
          }}
          onFocus={() => setFocused(true)}
          onBlur={() => setTimeout(() => setFocused(false), 150)}
          placeholder="CODE 또는 프로젝트명으로 검색…"
          className={cn(inputCls, selected && "pr-8")}
        />
        {selected && (
          <button
            type="button"
            onClick={handleClear}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200"
            aria-label="선택 해제"
          >
            ✕
          </button>
        )}
      </div>
      {focused && !selected && filtered.length > 0 && (
        <ul className="absolute left-0 right-0 top-full z-10 mt-1 max-h-64 overflow-y-auto rounded-md border border-zinc-200 bg-white shadow-lg dark:border-zinc-700 dark:bg-zinc-900">
          {filtered.map((p) => (
            <li key={p.id}>
              <button
                type="button"
                onMouseDown={(e) => {
                  e.preventDefault();
                  handleSelect(p);
                }}
                className="block w-full px-3 py-1.5 text-left text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800"
              >
                <span className="font-mono text-[11px] text-zinc-500">
                  {p.code || "—"}
                </span>{" "}
                {p.name || "(이름 없음)"}
              </button>
            </li>
          ))}
        </ul>
      )}
      {focused && !selected && filtered.length === 0 && query && (
        <div className="absolute left-0 right-0 top-full z-10 mt-1 rounded-md border border-zinc-200 bg-white px-3 py-2 text-xs text-zinc-500 shadow-lg dark:border-zinc-700 dark:bg-zinc-900">
          검색 결과가 없습니다.
        </div>
      )}
    </div>
  );
}
