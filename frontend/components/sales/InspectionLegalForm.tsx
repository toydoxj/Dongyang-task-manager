"use client";

import type { QuoteInput } from "@/lib/domain";
import { cn } from "@/lib/utils";

// 별표 23(1) — 건축물 구조형식별 조정비 키
const STRUCTURE_FACTOR_KEYS = [
  "철근콘크리트",
  "철골철근콘크리트",
  "PC조",
  "철골조",
  "조적조",
  "목구조",
  "특수구조",
];

// 별표 23(2) — 건축물 용도별 조정비 키
const USAGE_FACTOR_KEYS = [
  "업무용",
  "상업용",
  "지하도상가",
  "주거용",
  "특수용",
  "경기장",
  "체육관",
];

const COMPLEXITY_OPTIONS = ["단순", "보통", "복잡"];
const PREV_REPORT_OPTIONS = ["미제공", "CAD", "보고서+CAD"];
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

/** 시특법 점검 (정기/정밀점검/정밀안전진단) 자동 산정 입력 UI. PR-Q5b.
 *
 * 별표 22 base 인.일 보간 + 별표 23 조정비 + 제62조 보정 + 별표 25 직접경비
 * + 별표 26 추가과업까지 모두 자동 산정. 사용자가 structure_form/building_usage
 * 두 키 모두 채우면 backend가 자동 산정. 빈 값이면 manhours_override 흐름 fallback.
 */
export default function InspectionLegalForm({ value, onChange }: Props) {
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

  // 별표 26 자유 입력 (opt_other_items)
  const otherItems = value.opt_other_items ?? [];
  const updateOther = (idx: number, key: "name" | "amount", v: string | number): void => {
    const next = otherItems.map((it, i) =>
      i === idx ? { ...it, [key]: v } : it,
    );
    set("opt_other_items", next);
  };
  const addOther = (): void =>
    set("opt_other_items", [...otherItems, { name: "", amount: 0 }]);
  const removeOther = (idx: number): void =>
    set(
      "opt_other_items",
      otherItems.filter((_, i) => i !== idx),
    );

  return (
    <div className="space-y-3">
      <p className="rounded-md border border-blue-500/30 bg-blue-500/5 px-3 py-2 text-[11px] text-blue-700 dark:text-blue-400">
        구조형식·용도를 모두 선택하면 별표 22~25 자동 산정. 비우면 아래 수동
        입력(인.일) fallback.
      </p>

      {/* 별표 23 — 시설물별 조정비 */}
      <div className={sectionCls}>
        <h4 className="text-xs font-semibold text-stone-700 dark:text-stone-300">
          별표 23 — 시설물별 조정비
        </h4>
        <div className="grid grid-cols-2 gap-2">
          <label className="space-y-1">
            <div className={labelCls}>구조형식</div>
            <select
              className={inputCls}
              value={value.structure_form ?? ""}
              onChange={(e) => set("structure_form", e.target.value)}
            >
              <option value="">— 선택 —</option>
              {STRUCTURE_FACTOR_KEYS.map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
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
              {USAGE_FACTOR_KEYS.map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {/* 제62조 — 대가 보정 */}
      <div className={sectionCls}>
        <h4 className="text-xs font-semibold text-stone-700 dark:text-stone-300">
          제62조 — 대가 보정
        </h4>
        <div className="grid grid-cols-3 gap-2">
          <label className="space-y-1">
            <div className={labelCls}>경과년수</div>
            <input
              type="number"
              min={0}
              className={inputCls}
              placeholder="예: 30"
              value={value.aging_years ?? ""}
              onChange={(e) =>
                set(
                  "aging_years",
                  e.target.value ? Number(e.target.value) : null,
                )
              }
            />
          </label>
          <label className="space-y-1">
            <div className={labelCls}>구조복잡도</div>
            <select
              className={inputCls}
              value={value.complexity ?? "보통"}
              onChange={(e) => set("complexity", e.target.value)}
            >
              {COMPLEXITY_OPTIONS.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1">
            <div className={labelCls}>전차보고서</div>
            <select
              className={inputCls}
              value={value.prev_report ?? "미제공"}
              onChange={(e) => set("prev_report", e.target.value)}
            >
              {PREV_REPORT_OPTIONS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {/* 제61조 — 시설물 형태 */}
      <div className={sectionCls}>
        <h4 className="text-xs font-semibold text-stone-700 dark:text-stone-300">
          제61조 — 시설물 형태
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
            <div className={labelCls}>부속 면적 (㎡)</div>
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
              + 부속 면적 추가
            </button>
          </div>
        )}
      </div>

      {/* 별표 25 — 직접경비 단가 */}
      <div className={sectionCls}>
        <h4 className="text-xs font-semibold text-stone-700 dark:text-stone-300">
          별표 25 — 직접경비 단가
        </h4>
        <div className="grid grid-cols-2 gap-2">
          <label className="space-y-1">
            <div className={labelCls}>여비 1회 왕복 (1인)</div>
            <input
              type="number"
              min={0}
              className={inputCls}
              value={value.travel_unit_cost ?? 50000}
              onChange={(e) =>
                set("travel_unit_cost", Number(e.target.value))
              }
            />
          </label>
          <label className="space-y-1">
            <div className={labelCls}>특별인부 일당</div>
            <input
              type="number"
              min={0}
              className={inputCls}
              value={value.helper_daily_wage ?? 180000}
              onChange={(e) =>
                set("helper_daily_wage", Number(e.target.value))
              }
            />
          </label>
          <label className="space-y-1">
            <div className={labelCls}>차량 일일 손료</div>
            <input
              type="number"
              min={0}
              className={inputCls}
              value={value.vehicle_daily_cost ?? 30000}
              onChange={(e) =>
                set("vehicle_daily_cost", Number(e.target.value))
              }
            />
          </label>
          <label className="space-y-1">
            <div className={labelCls}>휘발유 ℓ당</div>
            <input
              type="number"
              min={0}
              className={inputCls}
              value={value.fuel_unit_price ?? 1800}
              onChange={(e) => set("fuel_unit_price", Number(e.target.value))}
            />
          </label>
          <label className="space-y-1">
            <div className={labelCls}>인쇄비 책당</div>
            <input
              type="number"
              min={0}
              className={inputCls}
              value={value.print_unit_cost ?? 5000}
              onChange={(e) => set("print_unit_cost", Number(e.target.value))}
            />
          </label>
          <label className="space-y-1">
            <div className={labelCls}>인쇄 부수</div>
            <input
              type="number"
              min={1}
              className={inputCls}
              value={value.print_copies ?? 3}
              onChange={(e) => set("print_copies", Number(e.target.value))}
            />
          </label>
          <label className="space-y-1 col-span-2">
            <div className={labelCls}>위험수당 % (10~20)</div>
            <input
              type="number"
              min={0}
              max={20}
              step={1}
              className={inputCls}
              value={value.risk_pct ?? 10}
              onChange={(e) => set("risk_pct", Number(e.target.value))}
            />
          </label>
        </div>
      </div>

      {/* 별표 26 추가과업 */}
      <div className={cn(sectionCls, "border-amber-500/30 bg-amber-500/5")}>
        <h4 className="text-xs font-semibold text-stone-700 dark:text-stone-300">
          별표 26 — 추가과업
        </h4>
        <p className="text-[10px] text-stone-600 dark:text-stone-400">
          구조해석·내진평가는 기본과업 인.일에 합산 (직접인건비 산정 포함).
          실측도면·기타는 직접경비에 합산.
        </p>

        {/* A. 실측도면 */}
        <label className="flex items-start gap-2">
          <input
            type="checkbox"
            className="mt-1"
            checked={value.opt_field_drawings ?? false}
            onChange={(e) => set("opt_field_drawings", e.target.checked)}
          />
          <div className="flex-1 space-y-1">
            <div className="text-xs">A. 실측도면 작성 (별표 26-1)</div>
            {value.opt_field_drawings && (
              <select
                className={inputCls}
                value={value.opt_field_drawings_scope ?? "기본"}
                onChange={(e) =>
                  set("opt_field_drawings_scope", e.target.value)
                }
              >
                <option value="기본">기본도면 (10%)</option>
                <option value="상세">기본 + 상세구조도 (20%)</option>
              </select>
            )}
          </div>
        </label>

        {/* B. 구조해석 */}
        <label className="flex items-start gap-2">
          <input
            type="checkbox"
            className="mt-1"
            checked={value.opt_structural_analysis ?? false}
            onChange={(e) =>
              set("opt_structural_analysis", e.target.checked)
            }
          />
          <div className="flex-1 space-y-1">
            <div className="text-xs">B. 구조해석 (별표 26-10-(3))</div>
            {value.opt_structural_analysis && (
              <div className="grid grid-cols-2 gap-1">
                <select
                  className={inputCls}
                  value={value.opt_analysis_struct_type ?? "RC계"}
                  onChange={(e) =>
                    set("opt_analysis_struct_type", e.target.value)
                  }
                >
                  <option value="RC계">RC·벽식·S조·SRC조</option>
                  <option value="PC조">PC조·주상복합</option>
                  <option value="특수구조">특수구조</option>
                </select>
                <input
                  type="number"
                  min={1}
                  className={inputCls}
                  placeholder="개소"
                  value={value.opt_analysis_count ?? 1}
                  onChange={(e) =>
                    set("opt_analysis_count", Number(e.target.value))
                  }
                />
              </div>
            )}
          </div>
        </label>

        {/* C. 내진성 평가 */}
        <label className="flex items-start gap-2">
          <input
            type="checkbox"
            className="mt-1"
            checked={value.opt_seismic_eval ?? false}
            onChange={(e) => set("opt_seismic_eval", e.target.checked)}
          />
          <div className="flex-1 space-y-1">
            <div className="text-xs">C. 내진성 평가 (별표 26-15)</div>
            {value.opt_seismic_eval && (
              <div className="space-y-1">
                <div className="flex gap-2 text-[11px]">
                  <label className="flex items-center gap-1">
                    <input
                      type="radio"
                      checked={(value.opt_seismic_multiplier ?? 2.0) === 2.0}
                      onChange={() => set("opt_seismic_multiplier", 2.0)}
                    />
                    간략 (×2.0)
                  </label>
                  <label className="flex items-center gap-1">
                    <input
                      type="radio"
                      checked={(value.opt_seismic_multiplier ?? 2.0) > 2.0}
                      onChange={() => set("opt_seismic_multiplier", 2.5)}
                    />
                    정밀 (2.5~3.0)
                  </label>
                </div>
                {(value.opt_seismic_multiplier ?? 2.0) > 2.0 && (
                  <div>
                    <input
                      type="range"
                      min={2.5}
                      max={3.0}
                      step={0.05}
                      className="w-full"
                      value={value.opt_seismic_multiplier ?? 2.5}
                      onChange={(e) =>
                        set(
                          "opt_seismic_multiplier",
                          Number(e.target.value),
                        )
                      }
                    />
                    <div className="text-center text-[11px] text-stone-600 dark:text-stone-400">
                      ×{(value.opt_seismic_multiplier ?? 2.5).toFixed(2)}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </label>

        {/* 자유 입력 */}
        <div className="space-y-1">
          <div className="text-xs">기타 (콘크리트 코어·해체·자문 등)</div>
          {otherItems.map((it, i) => (
            <div key={i} className="flex gap-1">
              <input
                className={cn(inputCls, "flex-1")}
                placeholder="항목명"
                value={it.name}
                onChange={(e) => updateOther(i, "name", e.target.value)}
              />
              <input
                type="number"
                min={0}
                className={cn(inputCls, "w-32")}
                placeholder="금액"
                value={it.amount}
                onChange={(e) =>
                  updateOther(i, "amount", Number(e.target.value))
                }
              />
              <button
                type="button"
                className="rounded border border-stone-300 px-2 text-xs hover:bg-stone-100 dark:border-stone-700 dark:hover:bg-stone-800"
                onClick={() => removeOther(i)}
              >
                ✕
              </button>
            </div>
          ))}
          <button
            type="button"
            className="rounded border border-stone-300 px-2 py-1 text-xs hover:bg-stone-100 dark:border-stone-700 dark:hover:bg-stone-800"
            onClick={addOther}
          >
            + 항목 추가
          </button>
        </div>
      </div>

      {/* fallback — manhours_override */}
      <div className={sectionCls}>
        <h4 className="text-xs font-semibold text-stone-700 dark:text-stone-300">
          수동 입력 (자동 산정 불가 시)
        </h4>
        <label className="space-y-1 block">
          <div className={labelCls}>
            조정 인.일 — xlsx 4계수 곱 결과 (자동 모드면 무시)
          </div>
          <input
            type="number"
            min={0}
            step={0.01}
            className={inputCls}
            placeholder="0.00"
            value={value.manhours_override ?? ""}
            onChange={(e) =>
              set(
                "manhours_override",
                e.target.value ? Number(e.target.value) : null,
              )
            }
          />
        </label>
      </div>
    </div>
  );
}
