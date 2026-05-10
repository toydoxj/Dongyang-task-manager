"use client";

import { useState } from "react";

import type { WeeklyReport } from "@/lib/api";

interface Props {
  data: WeeklyReport;
  onConfirm: () => void;
  onClose: () => void;
  publishing: boolean;
}

/** WEEK-004 — 발행 전 체크리스트 모달.
 * 수동 체크 4개를 모두 통과해야 [발행] 버튼 활성. 자동 평가 1개는 정보용. */
export default function PublishChecklist({
  data,
  onConfirm,
  onClose,
  publishing,
}: Props) {
  const [checks, setChecks] = useState({
    manual: false,
    completed: false,
    waiting: false,
    pdf: false,
  });
  const allChecked = Object.values(checks).every(Boolean);

  // 자동 평가 — 자동 집계인데 비어있는 섹션 수
  const autoEmpty = [
    data.completed.length,
    data.seal_log.length,
    data.sales.length,
    data.new_projects.length,
  ].filter((n) => n === 0).length;

  // 수동 입력 비어있음 안내용
  const manualEmpty =
    (data.notices.length === 0 ? 1 : 0) +
    (data.education.length === 0 ? 1 : 0) +
    (data.suggestions.length === 0 ? 1 : 0);

  const update = (key: keyof typeof checks) => (v: boolean) =>
    setChecks((s) => ({ ...s, [key]: v }));

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="주간업무일지 발행 전 확인"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget && !publishing) onClose();
      }}
    >
      <div className="w-full max-w-md rounded-xl border border-zinc-200 bg-white p-5 shadow-xl dark:border-zinc-800 dark:bg-zinc-900">
        <h3 className="text-base font-semibold">발행 전 확인</h3>
        <p className="mt-1 text-xs text-zinc-500">
          아래 항목을 확인하고 [발행] 버튼을 눌러주세요. 발행 시 WORKS Drive
          업로드 + 전 직원 알림 발송이 진행됩니다.
        </p>

        <ul className="mt-4 space-y-3">
          {/* 자동 평가 1개 */}
          <li className="flex items-start gap-2 rounded-md border border-zinc-200 bg-zinc-50 p-2 text-sm dark:border-zinc-800 dark:bg-zinc-950/40">
            <span
              className={
                autoEmpty === 0
                  ? "shrink-0 text-emerald-600 dark:text-emerald-400"
                  : "shrink-0 text-amber-600 dark:text-amber-400"
              }
            >
              {autoEmpty === 0 ? "✓" : "⚠"}
            </span>
            <div className="flex-1">
              <p className="font-medium text-zinc-800 dark:text-zinc-200">
                자동 집계 빈 섹션
              </p>
              <p className="text-[11px] text-zinc-500">
                {autoEmpty === 0
                  ? "모든 자동 집계 섹션에 데이터가 있습니다."
                  : `${autoEmpty}개 섹션이 비어있습니다 — 의도된 결과인지 확인하세요.`}
              </p>
            </div>
          </li>

          <CheckItem
            label="공지·교육·건의 검토 완료"
            hint={
              manualEmpty > 0
                ? `${manualEmpty}개 항목이 비어있습니다.`
                : "모두 입력되어 있습니다."
            }
            checked={checks.manual}
            onChange={update("manual")}
          />
          <CheckItem
            label="완료 프로젝트 검토"
            hint="누락된 프로젝트가 없는지 확인"
            checked={checks.completed}
            onChange={update("completed")}
          />
          <CheckItem
            label="보류·대기 프로젝트 확인"
            hint="장기 정체 항목 검토"
            checked={checks.waiting}
            onChange={update("waiting")}
          />
          <CheckItem
            label="PDF 미리보기 확인"
            hint="[PDF 확인] 버튼으로 1회 이상 검토"
            checked={checks.pdf}
            onChange={update("pdf")}
          />
        </ul>

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={publishing}
            className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
          >
            취소
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={!allChecked || publishing}
            className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
          >
            {publishing ? "발행 중..." : "발행"}
          </button>
        </div>
      </div>
    </div>
  );
}

function CheckItem({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <li>
      <label className="flex cursor-pointer items-start gap-2 rounded-md p-1 text-sm hover:bg-zinc-50 dark:hover:bg-zinc-800/40">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          className="mt-0.5 h-4 w-4 shrink-0"
        />
        <div className="flex-1">
          <p className="font-medium text-zinc-800 dark:text-zinc-200">{label}</p>
          <p className="text-[11px] text-zinc-500">{hint}</p>
        </div>
      </label>
    </li>
  );
}
