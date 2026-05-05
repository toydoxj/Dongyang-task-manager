"use client";

import { useEffect, useState } from "react";
import { useSWRConfig } from "swr";

import { useAuth } from "@/components/AuthGuard";
import {
  archiveSale,
  convertSale,
  createSale,
  updateSale,
} from "@/lib/api";
import {
  BID_STAGES,
  CONVERTIBLE_STAGES,
  type Sale,
  type SaleCreateRequest,
} from "@/lib/domain";
import { cn } from "@/lib/utils";

interface Props {
  /** null = 신규 모드, Sale = 수정 모드 */
  sale: Sale | null;
  /** 신규 모드 진입 트리거 */
  openNew: boolean;
  onClose: () => void;
  /** 저장/삭제 후 외부 리스트 갱신 트리거 (선택) */
  onChanged?: () => void;
  /** 신규 모드 시 자동 채울 담당자 (보통 본인) */
  defaultAssignee?: string;
}

const KIND_OPTIONS = ["수주영업", "기술지원"] as const;

export default function SalesEditModal({
  sale,
  openNew,
  onClose,
  onChanged,
  defaultAssignee,
}: Props) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const { mutate } = useSWRConfig();

  const [form, setForm] = useState<SaleCreateRequest>({ name: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const open = sale != null || openNew;
  const isEdit = sale != null;

  useEffect(() => {
    if (!open) return;
    setErr(null);
    if (sale) {
      setForm({
        name: sale.name,
        kind: sale.kind || undefined,
        stage: sale.stage || undefined,
        category: sale.category,
        estimated_amount: sale.estimated_amount ?? undefined,
        is_bid: sale.is_bid,
        client_id: sale.client_id || undefined,
        gross_floor_area: sale.gross_floor_area ?? undefined,
        floors_above: sale.floors_above ?? undefined,
        floors_below: sale.floors_below ?? undefined,
        building_count: sale.building_count ?? undefined,
        note: sale.note || undefined,
        submission_date: sale.submission_date || undefined,
        vat_inclusive: sale.vat_inclusive || undefined,
        performance_design_amount: sale.performance_design_amount ?? undefined,
        wind_tunnel_amount: sale.wind_tunnel_amount ?? undefined,
        parent_lead_id: sale.parent_lead_id || undefined,
        assignees: sale.assignees,
      });
    } else {
      setForm({
        name: "",
        kind: "수주영업",
        stage: "준비",
        assignees: defaultAssignee ? [defaultAssignee] : [],
      });
    }
  }, [open, sale, defaultAssignee]);

  if (!open) return null;

  const refreshSales = (): void => {
    void mutate(
      (key) => Array.isArray(key) && key[0] === "sales",
      undefined,
      { revalidate: true },
    );
    onChanged?.();
  };

  const handleSave = async (): Promise<void> => {
    if (!form.name?.trim()) {
      setErr("견적서명은 필수입니다.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      if (isEdit && sale) {
        await updateSale(sale.id, form);
      } else {
        await createSale(form);
      }
      refreshSales();
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "저장 실패");
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async (): Promise<void> => {
    if (!sale) return;
    if (!confirm(`"${sale.name}" 영업 건을 보관(archive) 처리할까요?`)) return;
    setBusy(true);
    setErr(null);
    try {
      await archiveSale(sale.id);
      refreshSales();
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "삭제 실패");
    } finally {
      setBusy(false);
    }
  };

  const handleConvert = async (): Promise<void> => {
    if (!sale) return;
    if (
      !confirm(
        `"${sale.name}" 영업을 수주 확정 — 메인 프로젝트로 전환할까요? 노션의 영업 단계는 "낙찰"로 자동 변경되고 새 프로젝트가 생성됩니다.`,
      )
    )
      return;
    setBusy(true);
    setErr(null);
    try {
      const project = await convertSale(sale.id);
      refreshSales();
      onClose();
      // 새 프로젝트 페이지로 이동
      if (typeof window !== "undefined") {
        window.location.href = `/project?id=${project.id}`;
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "수주 전환 실패");
    } finally {
      setBusy(false);
    }
  };

  const canConvert =
    isEdit &&
    isAdmin &&
    sale != null &&
    sale.kind === "수주영업" &&
    CONVERTIBLE_STAGES.includes(sale.stage) &&
    !sale.converted_project_id;

  const stageOptions =
    form.kind === "수주영업" ? BID_STAGES : ([] as readonly string[]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl rounded-lg border border-zinc-200 bg-white shadow-xl dark:border-zinc-700 dark:bg-zinc-900"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
          <h2 className="text-base font-semibold">
            {isEdit ? "영업 건 수정" : "새 영업"}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800"
            aria-label="닫기"
          >
            ×
          </button>
        </header>

        <div className="max-h-[70vh] space-y-3 overflow-y-auto px-4 py-3">
          {err && (
            <div className="rounded-md border border-red-500/40 bg-red-500/5 p-2 text-xs text-red-500">
              {err}
            </div>
          )}

          <Field label="견적서명">
            <input
              className={inputCls}
              value={form.name ?? ""}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="유형">
              <select
                className={inputCls}
                value={form.kind ?? ""}
                onChange={(e) =>
                  setForm({ ...form, kind: e.target.value || undefined })
                }
              >
                <option value="">—</option>
                {KIND_OPTIONS.map((k) => (
                  <option key={k} value={k}>
                    {k}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="단계">
              {stageOptions.length > 0 ? (
                <select
                  className={inputCls}
                  value={form.stage ?? ""}
                  onChange={(e) =>
                    setForm({ ...form, stage: e.target.value || undefined })
                  }
                >
                  <option value="">—</option>
                  {stageOptions.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  className={inputCls}
                  placeholder="기술지원 단계 (직접 입력)"
                  value={form.stage ?? ""}
                  onChange={(e) =>
                    setForm({ ...form, stage: e.target.value || undefined })
                  }
                />
              )}
            </Field>
          </div>

          <Field label="견적금액 (KRW)">
            <input
              type="number"
              className={inputCls}
              value={form.estimated_amount ?? ""}
              onChange={(e) =>
                setForm({
                  ...form,
                  estimated_amount: e.target.value
                    ? Number(e.target.value)
                    : undefined,
                })
              }
            />
          </Field>

          <div className="grid grid-cols-4 gap-2">
            <Field label="연면적 (㎡)">
              <input
                type="number"
                className={inputCls}
                value={form.gross_floor_area ?? ""}
                onChange={(e) =>
                  setForm({
                    ...form,
                    gross_floor_area: e.target.value
                      ? Number(e.target.value)
                      : undefined,
                  })
                }
              />
            </Field>
            <Field label="지상층수">
              <input
                type="number"
                className={inputCls}
                value={form.floors_above ?? ""}
                onChange={(e) =>
                  setForm({
                    ...form,
                    floors_above: e.target.value
                      ? Number(e.target.value)
                      : undefined,
                  })
                }
              />
            </Field>
            <Field label="지하층수">
              <input
                type="number"
                className={inputCls}
                value={form.floors_below ?? ""}
                onChange={(e) =>
                  setForm({
                    ...form,
                    floors_below: e.target.value
                      ? Number(e.target.value)
                      : undefined,
                  })
                }
              />
            </Field>
            <Field label="동수">
              <input
                type="number"
                className={inputCls}
                value={form.building_count ?? ""}
                onChange={(e) =>
                  setForm({
                    ...form,
                    building_count: e.target.value
                      ? Number(e.target.value)
                      : undefined,
                  })
                }
              />
            </Field>
          </div>

          <Field label="제출일">
            <input
              type="date"
              className={inputCls}
              value={form.submission_date ?? ""}
              onChange={(e) =>
                setForm({ ...form, submission_date: e.target.value || undefined })
              }
            />
          </Field>

          <Field label="담당자 (콤마 구분)">
            <input
              className={inputCls}
              value={(form.assignees ?? []).join(", ")}
              onChange={(e) =>
                setForm({
                  ...form,
                  assignees: e.target.value
                    .split(",")
                    .map((s) => s.trim())
                    .filter(Boolean),
                })
              }
            />
          </Field>

          <Field label="비고">
            <textarea
              className={cn(inputCls, "min-h-[64px]")}
              value={form.note ?? ""}
              onChange={(e) => setForm({ ...form, note: e.target.value })}
            />
          </Field>

          <label className="flex items-center gap-2 text-xs text-zinc-700 dark:text-zinc-300">
            <input
              type="checkbox"
              checked={form.is_bid ?? false}
              onChange={(e) => setForm({ ...form, is_bid: e.target.checked })}
            />
            입찰 여부
          </label>

          {isEdit && sale && sale.expected_revenue > 0 && (
            <div className="rounded-md border border-emerald-500/30 bg-emerald-500/5 px-3 py-2 text-xs text-emerald-700 dark:text-emerald-400">
              현재 기대매출: <strong>{sale.expected_revenue.toLocaleString("ko-KR")}원</strong>
              <span className="ml-1 text-[10px] text-zinc-500">(견적금액 × 단계별 수주확률)</span>
            </div>
          )}
        </div>

        <footer className="flex items-center justify-between gap-2 border-t border-zinc-200 px-4 py-3 dark:border-zinc-800">
          <div className="flex gap-2">
            {isEdit && isAdmin && (
              <button
                type="button"
                onClick={handleDelete}
                disabled={busy}
                className="rounded-md border border-red-500/40 px-3 py-1.5 text-xs text-red-500 hover:bg-red-500/10 disabled:opacity-50"
              >
                보관
              </button>
            )}
            {canConvert && (
              <button
                type="button"
                onClick={handleConvert}
                disabled={busy}
                className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs text-white hover:bg-emerald-700 disabled:opacity-50"
              >
                수주 전환 → 프로젝트
              </button>
            )}
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={busy}
              className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800 disabled:opacity-50"
            >
              취소
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={busy}
              className="rounded-md bg-zinc-900 px-3 py-1.5 text-xs text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300 disabled:opacity-50"
            >
              {busy ? "저장 중…" : "저장"}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}

const inputCls =
  "w-full rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="block text-[11px] font-medium text-zinc-600 dark:text-zinc-400">
        {label}
      </label>
      {children}
    </div>
  );
}
