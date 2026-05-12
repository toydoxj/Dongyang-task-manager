"use client";

/**
 * 프로젝트 진행단계를 '완료'/'타절'/'종결'로 변경하는 모달.
 * - 모두 완료일 default = 오늘 (수정 가능)
 * - 완료: stage="완료" + end_date
 * - 타절: stage="타절" + end_date + 타절금액(VAT 제외) + VAT → 용역비 수정
 * - 종결: stage="종결" + end_date + 용역비/VAT 0
 */

import { useMemo, useState } from "react";
import useSWR from "swr";

import { Field, inputCls } from "@/components/project/_shared";
import Modal from "@/components/ui/Modal";
import { getProjectLog, updateProject } from "@/lib/api";
import type { Project } from "@/lib/domain";
import { cn } from "@/lib/utils";

type Mode = "완료" | "타절" | "종결";

interface Props {
  project: Project;
  onClose: () => void;
  onSaved: () => void;
  /** 외부에서 모드를 prefill (칸반 드래그 흐름). 미지정 시 null로 시작. */
  defaultMode?: Mode;
}

export default function ProjectStageChangeModal({
  project,
  onClose,
  onSaved,
  defaultMode,
}: Props) {
  const today = new Date().toISOString().slice(0, 10);
  const [mode, setMode] = useState<Mode | null>(defaultMode ?? null);
  // endDate는 mode/prevEndDate에서 derived. 사용자가 직접 입력하면 override.
  const [endDateOverride, setEndDateOverride] = useState<string | null>(null);
  const [terminationAmount, setTerminationAmount] = useState("");
  const [terminationVat, setTerminationVat] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 이전 완료일 — 가장 최근 '완료 해제' log에서 추출 (재완료 시 default 복원)
  const { data: logData } = useSWR(["project-log", project.id], () =>
    getProjectLog(project.id),
  );
  const prevEndDate = useMemo<string>(() => {
    const items = logData?.items ?? [];
    // 시간순 ascending이라 뒤에서부터 (최신부터) 검색
    for (let i = items.length - 1; i >= 0; i--) {
      if (items[i].action === "완료 해제") {
        const m = items[i].title?.match(/이전 완료일:\s*(\d{4}-\d{2}-\d{2})/);
        if (m) return m[1];
      }
    }
    return "";
  }, [logData]);

  // endDate derived: 사용자 override > 완료 모드 + 이전 완료일 > 오늘
  // (이전엔 effect 내 setState였으나 set-state-in-effect 룰 위반 — useMemo로 변환)
  const endDate = useMemo<string>(() => {
    if (endDateOverride !== null) return endDateOverride;
    if (mode === "완료" && prevEndDate) return prevEndDate;
    return today;
  }, [endDateOverride, mode, prevEndDate, today]);

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
                onChange={(e) => setEndDateOverride(e.target.value)}
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
              <div className="space-y-1.5">
                {prevEndDate && (
                  <p className="rounded-md border border-amber-500/40 bg-amber-500/5 p-2 text-xs text-amber-700 dark:text-amber-300">
                    이전 완료일({prevEndDate})이 자동 복원됨. 변경 가능합니다.
                  </p>
                )}
                <p className="rounded-md border border-zinc-300 bg-zinc-50 p-2 text-xs text-zinc-600 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-400">
                  완료 시 용역비/VAT는 그대로 유지됩니다. 필요시 별도 편집에서 수정.
                </p>
              </div>
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
