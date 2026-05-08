"use client";

import { useEffect, useMemo, useState } from "react";

import QuoteResultPanel from "@/components/sales/QuoteResultPanel";
import { previewQuote } from "@/lib/api";
import { ENGINEER_GRADES, type EngineerGrade, type QuoteInput, type QuoteResult } from "@/lib/domain";
import { useClients } from "@/lib/hooks";
import { cn } from "@/lib/utils";

// 견적서 종류별 default 단가 등급 — backend _resolve_rate의 default_grade와 일치.
// 사용자가 등급 select에서 미선택(null) 시 표시 안내값.
const DEFAULT_ENGINEER_GRADE: Record<string, EngineerGrade> = {
  구조감리: "기술사",
  "3자검토": "특급기술자",
  // 그 외 모든 종류는 고급기술자
};
const defaultGradeFor = (qt: string): EngineerGrade =>
  DEFAULT_ENGINEER_GRADE[qt] ?? "고급기술자";

// 견적서 양식의 N/O열 옵션 — xlsx 실제 옵션과 일치
const STRUCTURE_FORMS = [
  "철근콘크리트구조",
  "철근콘크리트조(벽식구조)",
  "철근콘크리트구조 + 철골구조",
  "강구조(철골구조)",
  "하중전이구조",
  "PC구조, 복합구조",
  "플랜트구조",
  "특수구조",
];
const TYPE_RATES = [0.8, 0.9, 1.0, 1.1, 1.2];
const STRUCTURE_RATES = [0.5, 1.0, 1.2, 1.25, 1.5];
const COEFFICIENTS = [
  { value: 0.5, label: "0.5 (구조계산서만)" },
  { value: 1.0, label: "1.0 (계산서+도면)" },
];

interface Props {
  value: QuoteInput;
  onChange: (next: QuoteInput) => void;
  /** 부모(SalesEditModal)가 산출 결과를 알아야 저장 시 quote_form_data에 포함 가능 */
  onResultChange?: (result: QuoteResult | null) => void;
  /** true면 영업정보 탭 echo 필드(수신처/용역명/위치/규모) input을 disabled —
   *  사용자가 영업정보 탭에서 입력하도록 유도. */
  echoReadOnly?: boolean;
}

export default function QuoteForm({
  value,
  onChange,
  onResultChange,
  echoReadOnly = false,
}: Props) {
  const [result, setResult] = useState<QuoteResult | null>(null);
  const [loading, setLoading] = useState(false);
  // 수신처 회사명 자동완성용 — SalesEditModal에서도 useClients 호출하지만
  // SWR 캐시가 동일 키로 dedupe하므로 추가 fetch 비용 없음.
  const { data: clientsData } = useClients(true);

  // 산출에 필요한 핵심 입력만 변경되면 디바운스 호출.
  const pivotKey = useMemo(
    () =>
      JSON.stringify({
        qt: value.quote_type,
        a: value.gross_floor_area,
        t: value.type_rate,
        s: value.structure_rate,
        c: value.coefficient,
        mh: value.manhours_override,
        // 점검류 (PR-Q4) — 책임자/점검자 인.일 분리
        ir: value.inspection_responsible_days,
        ii: value.inspection_inspector_days,
        // 단가 등급
        eg: value.engineer_grade,
        bmar: value.bma_responsible_grade,
        bmai: value.bma_inspector_grade,
        // 내진성능평가 (PR-Q8) — 외업/내업/해석
        fo: value.field_outdoor_days,
        fi: value.field_indoor_days,
        ad: value.analysis_days,
        items: value.direct_expense_items,
        oh: value.overhead_pct,
        tf: value.tech_fee_pct,
        adj: value.adjustment_pct,
        tu: value.truncate_unit,
        fov: value.final_override,
        // legacy
        p: value.printing_fee,
        v: value.survey_fee,
        n: value.transport_persons,
      }),
    [value],
  );

  useEffect(() => {
    if (!value.gross_floor_area || value.gross_floor_area <= 0) {
      setResult(null);
      onResultChange?.(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    const handle = setTimeout(() => {
      previewQuote(value)
        .then((r) => {
          if (!cancelled) {
            setResult(r);
            onResultChange?.(r);
          }
        })
        .catch((e) => {
          // silent fail은 향후 디버깅 어려움 — 콘솔에 한 줄 남김
          // eslint-disable-next-line no-console
          console.error("previewQuote 실패:", e);
          if (!cancelled) {
            setResult(null);
            onResultChange?.(null);
          }
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, 300);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
    // pivotKey만 변경되면 재산출. value 전체에 의존하면 텍스트 입력 때마다 호출됨.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pivotKey]);

  const set = <K extends keyof QuoteInput>(k: K, v: QuoteInput[K]): void => {
    onChange({ ...value, [k]: v });
  };

  // 견적서 종류별 입력 분기 — 요율 3종은 구조설계계열만 표시. 점검류/내진평가는
  // 시특법·xlsx 보조 영역의 보간 결과를 사용자가 수동 입력하는 모델.
  // 구조검토는 자동 산출 없음 (사용자가 manhours_override 직접 입력) → 별도 분기.
  const qt = value.quote_type ?? "구조설계";
  const isStructReview = qt === "구조검토";
  const isStructDesignLike =
    qt === "구조설계" || qt === "성능기반내진설계" || qt === "기타";
  // 단가 등급 — BMA는 책임자/점검자 두 select 별도, 그 외는 단일 select.
  const isBma = qt === "건축물관리법점검";
  const isInspectionLegal =
    qt === "정기안전점검" || qt === "정밀점검" || qt === "정밀안전진단";
  const isInspectionBma = qt === "건축물관리법점검";
  const isSeismicEval = qt === "내진성능평가";
  // 내진평가 패키지 부속 (내진보강설계/3자검토)도 단일 인.일 입력 모델
  const isSimpleManhours =
    qt === "구조감리" ||
    qt === "현장기술지원" ||
    qt === "내진보강설계" ||
    qt === "3자검토";

  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
      {/* 입력 컬럼 */}
      <div className="space-y-3">
        {echoReadOnly && (
          <p className="rounded-md border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-[11px] text-amber-700 dark:text-amber-400">
            수신처·용역명·위치·규모는 영업 정보 탭에서 수정합니다 (여기서는 echo).
          </p>
        )}
        <Section title="수신처">
          <div className="grid grid-cols-2 gap-2">
            <Field label="회사명">
              <input
                className={inputCls}
                list="dy-clients-quote"
                value={value.recipient_company ?? ""}
                onChange={(e) => set("recipient_company", e.target.value)}
                disabled={echoReadOnly}
                placeholder={
                  clientsData
                    ? `목록 ${clientsData.count}개 자동완성, 발주처 변경 시 자동 갱신`
                    : ""
                }
              />
              <datalist id="dy-clients-quote">
                {clientsData?.items.map((c) => (
                  <option key={c.id} value={c.name}>
                    {c.category}
                  </option>
                ))}
              </datalist>
            </Field>
            <Field label="참조자">
              <input
                className={inputCls}
                value={value.recipient_person ?? ""}
                onChange={(e) => set("recipient_person", e.target.value)}
              />
            </Field>
            <Field label="전화">
              <input
                className={inputCls}
                value={value.recipient_phone ?? ""}
                onChange={(e) => set("recipient_phone", e.target.value)}
              />
            </Field>
            <Field label="E-mail">
              <input
                className={inputCls}
                value={value.recipient_email ?? ""}
                onChange={(e) => set("recipient_email", e.target.value)}
              />
            </Field>
          </div>
        </Section>

        <Section title="용역 정보">
          <Field label="용역명">
            <input
              className={inputCls}
              value={value.service_name ?? ""}
              onChange={(e) => set("service_name", e.target.value)}
              disabled={echoReadOnly}
            />
          </Field>
          <Field label="위치">
            <input
              className={inputCls}
              value={value.location ?? ""}
              onChange={(e) => set("location", e.target.value)}
              disabled={echoReadOnly}
            />
          </Field>
          <div className="grid grid-cols-4 gap-2">
            <Field label="연면적 (m²)">
              <input
                type="number"
                min={0}
                step={1}
                className={inputCls}
                value={value.gross_floor_area ?? ""}
                onChange={(e) =>
                  set(
                    "gross_floor_area",
                    e.target.value ? Number(e.target.value) : 0,
                  )
                }
                disabled={echoReadOnly}
              />
            </Field>
            <Field label="지상층수">
              <input
                type="number"
                min={0}
                step={1}
                className={inputCls}
                value={value.floors_above ?? ""}
                onChange={(e) =>
                  set(
                    "floors_above",
                    e.target.value ? Number(e.target.value) : null,
                  )
                }
                disabled={echoReadOnly}
              />
            </Field>
            <Field label="지하층수">
              <input
                type="number"
                min={0}
                step={1}
                className={inputCls}
                value={value.floors_below ?? ""}
                onChange={(e) =>
                  set(
                    "floors_below",
                    e.target.value ? Number(e.target.value) : null,
                  )
                }
                disabled={echoReadOnly}
              />
            </Field>
            <Field label="동수">
              <input
                type="number"
                min={0}
                step={1}
                className={inputCls}
                value={value.building_count ?? ""}
                onChange={(e) =>
                  set(
                    "building_count",
                    e.target.value ? Number(e.target.value) : null,
                  )
                }
                disabled={echoReadOnly}
              />
            </Field>
          </div>
          <Field label="구조형식">
            <select
              className={inputCls}
              value={value.structure_form ?? ""}
              onChange={(e) => set("structure_form", e.target.value)}
            >
              <option value="">—</option>
              {STRUCTURE_FORMS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </Field>
        </Section>

        <Section title="단가 등급">
          {isBma ? (
            <div className="grid grid-cols-2 gap-2">
              <Field label="책임자 등급 — 미선택 시 특급기술자">
                <select
                  className={inputCls}
                  value={value.bma_responsible_grade ?? ""}
                  onChange={(e) =>
                    set(
                      "bma_responsible_grade",
                      (e.target.value || null) as EngineerGrade | null,
                    )
                  }
                >
                  <option value="">— 기본값 (특급기술자) —</option>
                  {ENGINEER_GRADES.map((g) => (
                    <option key={g} value={g}>
                      {g}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="점검자 등급 — 미선택 시 초급기술자">
                <select
                  className={inputCls}
                  value={value.bma_inspector_grade ?? ""}
                  onChange={(e) =>
                    set(
                      "bma_inspector_grade",
                      (e.target.value || null) as EngineerGrade | null,
                    )
                  }
                >
                  <option value="">— 기본값 (초급기술자) —</option>
                  {ENGINEER_GRADES.map((g) => (
                    <option key={g} value={g}>
                      {g}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
          ) : (
            <Field
              label={`기술자 등급 — 미선택 시 기본값 (${defaultGradeFor(qt)})`}
            >
              <select
                className={inputCls}
                value={value.engineer_grade ?? ""}
                onChange={(e) =>
                  set(
                    "engineer_grade",
                    (e.target.value || null) as EngineerGrade | null,
                  )
                }
              >
                <option value="">— 기본값 ({defaultGradeFor(qt)}) —</option>
                {ENGINEER_GRADES.map((g) => (
                  <option key={g} value={g}>
                    {g}
                  </option>
                ))}
              </select>
            </Field>
          )}
          <p className="text-[11px] text-stone-500">
            한국엔지니어링협회 통계법 단가 (건설분야, 매년 1월 갱신).
          </p>
        </Section>

        {isStructDesignLike && (
          <Section title="요율 · 인.일">
            <div className="grid grid-cols-3 gap-2">
              <Field label="종별 요율">
                <select
                  className={inputCls}
                  value={value.type_rate ?? 1}
                  onChange={(e) => set("type_rate", Number(e.target.value))}
                >
                  {TYPE_RATES.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="구조방식 요율">
                <select
                  className={inputCls}
                  value={value.structure_rate ?? 1}
                  onChange={(e) =>
                    set("structure_rate", Number(e.target.value))
                  }
                >
                  {STRUCTURE_RATES.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="계수">
                <select
                  className={inputCls}
                  value={value.coefficient ?? 1}
                  onChange={(e) => set("coefficient", Number(e.target.value))}
                >
                  {COEFFICIENTS.map((c) => (
                    <option key={c.value} value={c.value}>
                      {c.label}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            <Field label="투입인원 (인.일) — 비우면 연면적·요율로 자동 산출">
              <input
                type="number"
                min={0}
                step={1}
                className={inputCls}
                placeholder="자동 산출"
                value={value.manhours_override ?? ""}
                onChange={(e) =>
                  set(
                    "manhours_override",
                    e.target.value ? Number(e.target.value) : null,
                  )
                }
              />
            </Field>
          </Section>
        )}

        {isStructReview && (
          <Section title="투입인원">
            <Field label="인.일 — 직접 입력 (자동 산출 없음)">
              <input
                type="number"
                min={0}
                step={1}
                className={inputCls}
                placeholder="예: 30"
                value={value.manhours_override ?? ""}
                onChange={(e) =>
                  set(
                    "manhours_override",
                    e.target.value ? Number(e.target.value) : null,
                  )
                }
              />
            </Field>
            <p className="text-[11px] text-stone-500">
              구조검토는 단가 310,884원/일 (고급기술자) × 입력 인.일로 산출.
              요율은 적용되지 않음.
            </p>
          </Section>
        )}

        {isSimpleManhours && (
          <Section title="투입인원">
            <Field
              label={
                qt === "구조감리"
                  ? "투입인원 (인.일) — 현장 방문회수 × 3 (예: 27회 × 3 = 81)"
                  : qt === "내진보강설계"
                    ? "투입인원 (인.일) — 단가 310,884원/일 (고급기술자, 건설)"
                    : qt === "3자검토"
                      ? "투입인원 (인.일) — 단가 310,884원/일 (고급기술자, 건설)"
                      : "투입인원 (인.일) — 회당 3 기준 권장"
              }
            >
              <input
                type="number"
                min={0}
                step={1}
                className={inputCls}
                placeholder="0"
                value={value.manhours_override ?? ""}
                onChange={(e) =>
                  set(
                    "manhours_override",
                    e.target.value ? Number(e.target.value) : null,
                  )
                }
              />
            </Field>
          </Section>
        )}

        {isInspectionLegal && (
          <Section title="투입인원">
            <Field label="조정 인.일 — 시특법 sheet의 4계수 곱 결과 (예: 15.24)">
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
            </Field>
            <p className="text-[11px] text-stone-500">
              xlsx 시특법 sheet의 H40 = ROUNDDOWN(C40·D40·E40·F40·G40, 2)
              결과를 그대로 입력하세요. 직접경비는 아래 항목 list로.
            </p>
          </Section>
        )}

        {isInspectionBma && (
          <Section title="투입인원 (책임자 · 점검자)">
            <div className="grid grid-cols-2 gap-2">
              <Field label="책임자 인.일">
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
              </Field>
              <Field label="점검자 인.일">
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
              </Field>
            </div>
            <p className="text-[11px] text-stone-500">
              건축물관리법점검은 책임자(456,237원/일) + 점검자(235,459원/일)
              등급별 단가 분리 산출.
            </p>
          </Section>
        )}

        {isSeismicEval && (
          <Section title="투입인원 (현장조사 · 해석)">
            <Field label="구조도면 보유 — 면적 입력 시 자동 보간 채움 (PR-Q8b)">
              <select
                className={inputCls}
                value={
                  value.has_structural_drawings === true
                    ? "Y"
                    : value.has_structural_drawings === false
                      ? "N"
                      : ""
                }
                onChange={(e) =>
                  set(
                    "has_structural_drawings",
                    e.target.value === "Y"
                      ? true
                      : e.target.value === "N"
                        ? false
                        : null,
                  )
                }
              >
                <option value="">— 수동 입력 모드 —</option>
                <option value="Y">유 (도면 있음)</option>
                <option value="N">무 (도면 없음)</option>
              </select>
            </Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="현장조사 외업 인.일">
                <input
                  type="number"
                  min={0}
                  step={0.001}
                  className={inputCls}
                  placeholder="예: 22.641"
                  value={value.field_outdoor_days ?? ""}
                  onChange={(e) =>
                    set(
                      "field_outdoor_days",
                      e.target.value ? Number(e.target.value) : null,
                    )
                  }
                />
              </Field>
              <Field label="현장조사 내업 인.일">
                <input
                  type="number"
                  min={0}
                  step={0.001}
                  className={inputCls}
                  placeholder="예: 12"
                  value={value.field_indoor_days ?? ""}
                  onChange={(e) =>
                    set(
                      "field_indoor_days",
                      e.target.value ? Number(e.target.value) : null,
                    )
                  }
                />
              </Field>
            </div>
            <Field label="해석 인.일 — 구조해석 소요 인.일 (xlsx I56)">
              <input
                type="number"
                min={0}
                step={0.001}
                className={inputCls}
                placeholder="예: 67.667"
                value={value.analysis_days ?? ""}
                onChange={(e) =>
                  set(
                    "analysis_days",
                    e.target.value ? Number(e.target.value) : null,
                  )
                }
              />
            </Field>
            <p className="text-[11px] text-stone-500">
              연면적·구조도면 유무·해석방법·등급 보간 table은 xlsx에서 확인 후
              인.일 3종을 직접 입력하세요. 단가는 300,980원/일 (기술자) 고정.
            </p>
          </Section>
        )}

        <Section title="직접경비">
          {(value.direct_expense_items ?? []).map((item, idx) => (
            <div key={idx} className="flex items-center gap-2">
              <input
                className={cn(inputCls, "flex-1")}
                placeholder="항목명 (예: 보고서 인쇄비)"
                value={item.name}
                onChange={(e) => {
                  const next = [...(value.direct_expense_items ?? [])];
                  next[idx] = { ...item, name: e.target.value };
                  set("direct_expense_items", next);
                }}
              />
              <input
                type="number"
                min={0}
                className={cn(inputCls, "w-32")}
                placeholder="금액"
                value={item.amount || ""}
                onChange={(e) => {
                  const next = [...(value.direct_expense_items ?? [])];
                  next[idx] = {
                    ...item,
                    amount: e.target.value ? Number(e.target.value) : 0,
                  };
                  set("direct_expense_items", next);
                }}
              />
              <button
                type="button"
                onClick={() => {
                  const next = [...(value.direct_expense_items ?? [])];
                  next.splice(idx, 1);
                  set("direct_expense_items", next);
                }}
                className="rounded border border-zinc-300 px-2 py-1 text-xs hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
                aria-label="삭제"
              >
                ✕
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={() =>
              set("direct_expense_items", [
                ...(value.direct_expense_items ?? []),
                { name: "", amount: 0 },
              ])
            }
            className="rounded-md border border-dashed border-zinc-400 px-3 py-1.5 text-xs text-zinc-600 hover:bg-zinc-50 dark:border-zinc-600 dark:text-zinc-400 dark:hover:bg-zinc-800"
          >
            + 항목 추가
          </button>
        </Section>

        <Section title="제경비 · 기술료 · 조정">
          <div className="grid grid-cols-3 gap-2">
            <Field label="제경비 (%)">
              <input
                type="number"
                min={0}
                step={1}
                className={inputCls}
                value={value.overhead_pct ?? 110}
                onChange={(e) =>
                  set("overhead_pct", e.target.value ? Number(e.target.value) : 110)
                }
              />
            </Field>
            <Field label="기술료 (%)">
              <input
                type="number"
                min={0}
                step={1}
                className={inputCls}
                value={value.tech_fee_pct ?? 20}
                onChange={(e) =>
                  set("tech_fee_pct", e.target.value ? Number(e.target.value) : 20)
                }
              />
            </Field>
            <Field label="당사 조정 (%)">
              <input
                type="number"
                min={0}
                max={200}
                step={1}
                className={inputCls}
                value={value.adjustment_pct ?? 87}
                onChange={(e) =>
                  set("adjustment_pct", e.target.value ? Number(e.target.value) : 87)
                }
              />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Field label="절삭 단위">
              <select
                className={inputCls}
                value={value.truncate_unit ?? 1_000_000}
                onChange={(e) =>
                  set("truncate_unit", Number(e.target.value))
                }
                disabled={value.final_override != null}
              >
                <option value={1_000_000}>백만 미만</option>
                <option value={100_000}>십만 미만</option>
                <option value={10_000}>만 미만</option>
                <option value={0}>절삭 없음</option>
              </select>
            </Field>
            <Field label="최종 금액 직접 입력 (선택)">
              <input
                type="number"
                min={0}
                step={1}
                className={inputCls}
                placeholder="비우면 자동 절삭"
                value={value.final_override ?? ""}
                onChange={(e) =>
                  set(
                    "final_override",
                    e.target.value ? Number(e.target.value) : null,
                  )
                }
              />
            </Field>
          </div>
          <label className="flex items-center gap-2 text-xs text-zinc-700 dark:text-zinc-300">
            <input
              type="checkbox"
              className="size-3.5 accent-emerald-600"
              checked={!!value.vat_included}
              onChange={(e) => set("vat_included", e.target.checked)}
            />
            VAT 포함 표시 (산출 결과·PDF에 공급가액·VAT·합계 추가)
          </label>
        </Section>

        <Section title="기타">
          <Field label="지불방법">
            <input
              className={inputCls}
              placeholder="쌍방의 협의에 의함."
              value={value.payment_terms ?? ""}
              onChange={(e) => set("payment_terms", e.target.value)}
            />
          </Field>
          <Field label="특이사항">
            <textarea
              className={cn(inputCls, "min-h-[60px]")}
              value={value.special_notes ?? ""}
              onChange={(e) => set("special_notes", e.target.value)}
            />
          </Field>
        </Section>
      </div>

      {/* 산출 결과 컬럼 */}
      <div className="lg:sticky lg:top-2 lg:h-fit">
        <h3 className="mb-2 text-xs font-semibold text-emerald-700 dark:text-emerald-400">
          산출 결과
        </h3>
        <QuoteResultPanel
          result={result}
          loading={loading}
          vatIncluded={!!value.vat_included}
        />
      </div>
    </div>
  );
}

const inputCls =
  "w-full rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900";

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2 rounded-md border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900">
      <h4 className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
        {title}
      </h4>
      {children}
    </div>
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
    <div className="space-y-1">
      <label className="block text-[11px] font-medium text-zinc-600 dark:text-zinc-400">
        {label}
      </label>
      {children}
    </div>
  );
}
