"use client";

/**
 * 프로젝트 진행단계를 '완료'/'타절'/'종결'로 변경하는 모달.
 * - 모두 완료일 default = 오늘 (수정 가능)
 * - 완료: stage="완료" + end_date
 * - 타절: stage="타절" + end_date + 타절금액(VAT 제외) + VAT → 용역비 수정
 * - 종결: stage="종결" + end_date + 용역비/VAT 0
 */

import { useState } from "react";

import Modal from "@/components/ui/Modal";
import { updateProject } from "@/lib/api";
import type { Project } from "@/lib/domain";
import { cn } from "@/lib/utils";

interface Props {
  project: Project;
  onClose: () => void;
  onSaved: () => void;
}

type Mode = "완료" | "타절" | "종결";

export default function ProjectStageChangeModal({
  project,
  onClose,
  onSaved,
}: Props) {
  const today = new Date().toISOString().slice(0, 10);
  const [mode, setMode] = useState<Mode | null>(null);
  const [endDate, setEndDate] = useState(today);
  const [terminationAmount, setTerminationAmount] = useState("");
  const [terminationVat, setTerminationVat] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (): Promise<void> => {
    if (!mode) return;
    setBusy(true);
    setError(null);
    try {
      const body: import("@/lib/domain").ProjectUpdateRequest = {
        stage: mode,
        end_date: endDate || today,
      };
      if (mode === "타절") {
        const amt = parseAmount(terminationAmount);
        const v = parseAmount(terminationVat);
        if (amt == null) {
          setError("타절금액을 입력하세요");
          setBusy(false);
          return;
        }
        body.contract_amount = amt;
        body.vat = v ?? 0;
      } else if (mode === "종결") {
        body.contract_amount = 0;
        body.vat = 0;
      }
      await updateProject(project.id, body);
      onSaved();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "저장 실패");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={true} onClose={onClose} title="진행단계 변경" size="md">
      <div className="space-y-4">
        {/* mode 선택 */}
        <div className="grid grid-cols-3 gap-2">
          {(["완료", "타절", "종결"] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              className={cn(
                "rounded-md border px-3 py-2 text-sm font-medium transition-colors",
                mode === m
                  ? m === "완료"
                    ? "border-emerald-500 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                    : m === "타절"
                      ? "border-red-500 bg-red-500/10 text-red-700 dark:text-red-300"
                      : "border-zinc-500 bg-zinc-500/10 text-zinc-700 dark:text-zinc-300"
                  : "border-zinc-300 hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800",
              )}
            >
              {m}
            </button>
          ))}
        </div>

        {mode && (
          <>
            {/* 완료일 */}
            <Field label="완료일">
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className={inputCls}
              />
            </Field>

            {/* 타절: 금액 + VAT */}
            {mode === "타절" && (
              <div className="grid grid-cols-2 gap-3">
                <Field label="타절금액 (VAT 제외)">
                  <input
                    type="text"
                    inputMode="numeric"
                    value={terminationAmount}
                    onChange={(e) =>
                      setTerminationAmount(formatComma(e.target.value))
                    }
                    placeholder="0"
                    className={inputCls}
                  />
                </Field>
                <Field label="VAT">
                  <input
                    type="text"
                    inputMode="numeric"
                    value={terminationVat}
                    onChange={(e) =>
                      setTerminationVat(formatComma(e.target.value))
                    }
                    placeholder="0"
                    className={inputCls}
                  />
                </Field>
              </div>
            )}

            {mode === "종결" && (
              <p className="rounded-md border border-zinc-300 bg-zinc-50 p-2 text-xs text-zinc-600 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-400">
                종결 시 용역비와 VAT가 자동으로 ₩0으로 변경됩니다.
              </p>
            )}
            {mode === "완료" && (
              <p className="rounded-md border border-zinc-300 bg-zinc-50 p-2 text-xs text-zinc-600 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-400">
                완료 시 용역비/VAT는 그대로 유지됩니다. 필요시 별도 편집에서 수정.
              </p>
            )}
          </>
        )}

        {error && (
          <p className="rounded-md border border-red-500/40 bg-red-500/5 p-2 text-xs text-red-400">
            {error}
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
            disabled={busy || !mode}
            className="rounded-md bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
          >
            {busy ? "저장 중..." : "저장"}
          </button>
        </footer>
      </div>
    </Modal>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block text-xs">
      <span className="mb-1 block text-zinc-500">{label}</span>
      {children}
    </label>
  );
}

const inputCls =
  "w-full rounded-md border border-zinc-300 bg-white px-2.5 py-1.5 text-sm outline-none focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-950";

/** "1,234,567" 형태 그대로 표시 */
function formatComma(raw: string): string {
  const digits = raw.replace(/[^\d]/g, "");
  if (!digits) return "";
  return Number(digits).toLocaleString("ko-KR");
}

function parseAmount(s: string): number | null {
  if (!s.trim()) return null;
  const n = Number(s.replace(/[^\d]/g, ""));
  return Number.isFinite(n) ? n : null;
}
