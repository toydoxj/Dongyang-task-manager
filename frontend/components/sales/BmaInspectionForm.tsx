"use client";

import type { QuoteInput } from "@/lib/domain";
import { cn } from "@/lib/utils";

// 별표 3-(2) 건축물관리법 용도 — 산정표 sheet 1 M7~M20 + 지침 본문
const BMA_USAGE_OPTIONS = [
  "근린생활시설",
  "공동주택",
  "판매시설",
  "장례식장",
  "교육연구시설",
  "노유자시설",
  "위락시설",
  "관광휴게시설",
  "문화및집회시설",
  "운수시설",
  "의료시설",
  "도서관",
  "운동시설",
  "관광숙박시설",
];

const FACILITY_TYPES = ["기본", "인접", "군집(소)", "군집(대)", "혼합"];

const inputCls =
  "w-full rounded-md border border-stone-300 bg-white px-2 py-1 text-sm shadow-sm dark:border-stone-700 dark:bg-stone-900 focus:outline-none focus:ring-2 focus:ring-amber-500/30";
const sectionCls =
  "rounded-md border border-stone-200 bg-stone-50/40 p-3 space-y-2 dark:border-stone-800 dark:bg-stone-900/30";
const labelCls = "text-[11px] font-medium text-stone-600 dark:text-stone-400";

interface Props {
  value: QuoteInput;
  onChange: (next: QuoteInput) => void;
}

/** 건축물관리법 정기점검 자동 산정 입력 UI (PR-Q4b).
 *
 * 산정표 (사장 운영 표준) 산식 기반:
 *  - 별표 1 보간 (책임자·점검자 분리)
 *  - 별표 3 보정 (경과년수·용도)
 *  - 제37조 군집건축물
 *  - 제38조 추가 보정 (구조 생략 0.8 / 급수 생략 0.9)
 *  - 제39조 선택과업비 (마감재 해체) 자유 입력
 */
export default function BmaInspectionForm({ value, onChange }: Props) {
  const set = <K extends keyof QuoteInput>(k: K, v: QuoteInput[K]): void => {
    onChange({ ...value, [k]: v });
  };

  const facilityType = value.facility_type ?? "기본";
  const showSubAreas = facilityType !== "기본";
  const subAreas = value.sub_facility_areas ?? [];

  const updateSubArea = (idx: number, v: number): void => {
    const next = [...subAreas];
    next[idx] = v;
    set("sub_facility_areas", next);
  };
  const addSubArea = (): void =>
    set("sub_facility_areas", [...subAreas, 0]);
  const removeSubArea = (idx: number): void =>
    set(
      "sub_facility_areas",
      subAreas.filter((_, i) => i !== idx),
    );

  return (
    <div className="space-y-3">
      <p className="rounded-md border border-blue-500/30 bg-blue-500/5 px-3 py-2 text-[11px] text-blue-700 dark:text-blue-400">
        점검 종류·용도를 채우면 산정표(별표 1~3) 자동 산정. 비우면 아래 수동
        입력(책임자·점검자 인.일) fallback.
      </p>

      {/* 점검 종류 + 용도 (별표 3-2) */}
      <div className={sectionCls}>
        <h4 className="text-xs font-semibold text-stone-700 dark:text-stone-300">
          점검 종류 · 용도 (별표 3-2)
        </h4>
        <div className="grid grid-cols-2 gap-2">
          <label className="space-y-1">
            <div className={labelCls}>점검 종류</div>
            <select
              className={inputCls}
              value={value.bma_inspection_type ?? ""}
              onChange={(e) => set("bma_inspection_type", e.target.value)}
            >
              <option value="">— 선택 —</option>
              <option value="정기">정기점검</option>
              <option value="정기+구조">정기점검 + 구조안전 추가</option>
            </select>
          </label>
          <label className="space-y-1">
            <div className={labelCls}>용도</div>
            <select
              className={inputCls}
              value={value.building_usage ?? ""}
              onChange={(e) => set("building_usage", e.target.value)}
            >
              <option value="">— 선택 —</option>
              {BMA_USAGE_OPTIONS.map((u) => (
                <option key={u} value={u}>
                  {u}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {/* 경과년수 (별표 3-1) */}
      <div className={sectionCls}>
        <h4 className="text-xs font-semibold text-stone-700 dark:text-stone-300">
          경과년수 (별표 3-1)
        </h4>
        <label className="space-y-1 block">
          <div className={labelCls}>
            준공년도{" "}
            {value.completion_year ? (
              <span className="text-stone-500">
                (경과 {Math.max(0, new Date().getFullYear() - value.completion_year)}년)
              </span>
            ) : null}
          </div>
          <input
            type="number"
            min={1900}
            max={2100}
            className={inputCls}
            placeholder="예: 1996"
            value={value.completion_year ?? ""}
            onChange={(e) =>
              set(
                "completion_year",
                e.target.value ? Number(e.target.value) : null,
              )
            }
          />
        </label>
      </div>

      {/* 제37조 군집건축물 */}
      <div className={sectionCls}>
        <h4 className="text-xs font-semibold text-stone-700 dark:text-stone-300">
          제37조 — 군집건축물
        </h4>
        <label className="space-y-1 block">
          <div className={labelCls}>형태</div>
          <select
            className={inputCls}
            value={facilityType}
            onChange={(e) => set("facility_type", e.target.value)}
          >
            {FACILITY_TYPES.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
        </label>
        {showSubAreas && (
          <div className="space-y-1">
            <div className={labelCls}>부속 동 면적 (㎡)</div>
            {subAreas.map((a, i) => (
              <div key={i} className="flex gap-1">
                <input
                  type="number"
                  min={0}
                  className={inputCls}
                  value={a}
                  onChange={(e) => updateSubArea(i, Number(e.target.value))}
                />
                <button
                  type="button"
                  className="rounded border border-stone-300 px-2 text-xs hover:bg-stone-100 dark:border-stone-700 dark:hover:bg-stone-800"
                  onClick={() => removeSubArea(i)}
                >
                  ✕
                </button>
              </div>
            ))}
            <button
              type="button"
              className="rounded border border-stone-300 px-2 py-1 text-xs hover:bg-stone-100 dark:border-stone-700 dark:hover:bg-stone-800"
              onClick={addSubArea}
            >
              + 부속 동 추가
            </button>
          </div>
        )}
      </div>

      {/* 제38조 추가 보정 */}
      <div className={sectionCls}>
        <h4 className="text-xs font-semibold text-stone-700 dark:text-stone-300">
          제38조 — 추가 보정
        </h4>
        <label className="flex items-center gap-2 text-[11px]">
          <input
            type="checkbox"
            checked={value.bma_skip_structural ?? false}
            onChange={(e) => set("bma_skip_structural", e.target.checked)}
          />
          ② 구조안전 점검 생략 (× 0.8)
        </label>
        <label className="flex items-center gap-2 text-[11px]">
          <input
            type="checkbox"
            checked={value.bma_skip_utility ?? false}
            onChange={(e) => set("bma_skip_utility", e.target.checked)}
          />
          ③ 급수·배수·냉난방·환기 생략 (× 0.9)
        </label>
      </div>

      {/* 제36조 직접경비 + 제39조 선택과업 */}
      <div className={cn(sectionCls, "border-amber-500/30 bg-amber-500/5")}>
        <h4 className="text-xs font-semibold text-stone-700 dark:text-stone-300">
          직접경비 · 선택과업
        </h4>
        <p className="text-[11px] text-stone-700 dark:text-stone-400">
          제36조 — 직접경비 100,000원 일괄 (자동 적용)
        </p>
        <label className="space-y-1 block">
          <div className={labelCls}>
            제39조 선택과업비 — 마감재 해체·복구 (자유 입력)
          </div>
          <input
            type="number"
            min={0}
            className={inputCls}
            placeholder="0"
            value={value.bma_optional_task_amount || ""}
            onChange={(e) =>
              set(
                "bma_optional_task_amount",
                e.target.value ? Number(e.target.value) : 0,
              )
            }
          />
        </label>
      </div>

      {/* fallback — 수동 입력 */}
      <div className={sectionCls}>
        <h4 className="text-xs font-semibold text-stone-700 dark:text-stone-300">
          수동 입력 (자동 산정 불가 시)
        </h4>
        <div className="grid grid-cols-2 gap-2">
          <label className="space-y-1">
            <div className={labelCls}>책임자 인.일</div>
            <input
              type="number"
              min={0}
              step={0.01}
              className={inputCls}
              placeholder="예: 1.44"
              value={value.inspection_responsible_days ?? ""}
              onChange={(e) =>
                set(
                  "inspection_responsible_days",
                  e.target.value ? Number(e.target.value) : null,
                )
              }
            />
          </label>
          <label className="space-y-1">
            <div className={labelCls}>점검자 인.일</div>
            <input
              type="number"
              min={0}
              step={0.01}
              className={inputCls}
              placeholder="예: 0.44"
              value={value.inspection_inspector_days ?? ""}
              onChange={(e) =>
                set(
                  "inspection_inspector_days",
                  e.target.value ? Number(e.target.value) : null,
                )
              }
            />
          </label>
        </div>
        <p className="text-[10px] text-stone-500">
          기술사(특급) 456,237원 / 초급기술자 235,459원 (산정표 default).
        </p>
      </div>
    </div>
  );
}
