"use client";

import { useEffect, useMemo, useState } from "react";

import QuoteResultPanel from "@/components/sales/QuoteResultPanel";
import { previewQuote } from "@/lib/api";
import type { QuoteInput, QuoteResult } from "@/lib/domain";
import { cn } from "@/lib/utils";

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
}

export default function QuoteForm({ value, onChange, onResultChange }: Props) {
  const [result, setResult] = useState<QuoteResult | null>(null);
  const [loading, setLoading] = useState(false);

  // 산출에 필요한 핵심 입력만 변경되면 디바운스 호출.
  const pivotKey = useMemo(
    () =>
      JSON.stringify({
        a: value.gross_floor_area,
        t: value.type_rate,
        s: value.structure_rate,
        c: value.coefficient,
        p: value.printing_fee,
        v: value.survey_fee,
        n: value.transport_persons,
        adj: value.adjustment_pct,
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
        .catch(() => {
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

  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
      {/* 입력 컬럼 */}
      <div className="space-y-3">
        <Section title="수신처">
          <div className="grid grid-cols-2 gap-2">
            <Field label="회사명">
              <input
                className={inputCls}
                value={value.recipient_company ?? ""}
                onChange={(e) => set("recipient_company", e.target.value)}
              />
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
            />
          </Field>
          <Field label="위치">
            <input
              className={inputCls}
              value={value.location ?? ""}
              onChange={(e) => set("location", e.target.value)}
            />
          </Field>
          <div className="grid grid-cols-2 gap-2">
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
              />
            </Field>
            <Field label="층수">
              <input
                className={inputCls}
                placeholder="지하1층/지상3층"
                value={value.floors_text ?? ""}
                onChange={(e) => set("floors_text", e.target.value)}
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

        <Section title="요율">
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
        </Section>

        <Section title="직접경비 + 조정">
          <div className="grid grid-cols-3 gap-2">
            <Field label="보고서인쇄비 (원)">
              <input
                type="number"
                className={inputCls}
                value={value.printing_fee ?? ""}
                onChange={(e) =>
                  set("printing_fee", e.target.value ? Number(e.target.value) : 0)
                }
              />
            </Field>
            <Field label="추가조사비 (원)">
              <input
                type="number"
                className={inputCls}
                value={value.survey_fee ?? ""}
                onChange={(e) =>
                  set("survey_fee", e.target.value ? Number(e.target.value) : 0)
                }
              />
            </Field>
            <Field label="교통비 (인.일)">
              <input
                type="number"
                min={0}
                step={1}
                className={inputCls}
                value={value.transport_persons ?? ""}
                onChange={(e) =>
                  set(
                    "transport_persons",
                    e.target.value ? Number(e.target.value) : 0,
                  )
                }
              />
            </Field>
          </div>
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
        <QuoteResultPanel result={result} loading={loading} />
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
