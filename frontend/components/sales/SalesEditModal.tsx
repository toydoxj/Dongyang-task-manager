"use client";

import { useEffect, useState } from "react";
import { useSWRConfig } from "swr";

import { useAuth } from "@/components/AuthGuard";
import {
  archiveSale,
  convertSale,
  createSale,
  linkSaleToProject,
  updateSale,
} from "@/lib/api";
import {
  BID_STAGES,
  CONVERTIBLE_STAGES,
  type Project,
  type Sale,
  type SaleCreateRequest,
} from "@/lib/domain";
import { useProjects } from "@/lib/hooks";
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
  const [linkPickerOpen, setLinkPickerOpen] = useState(false);

  const open = sale != null || openNew;
  const isEdit = sale != null;

  useEffect(() => {
    if (!open) return;
    setErr(null);
    if (sale) {
      setForm({
        name: sale.name,
        code: sale.code || undefined,
        kind: sale.kind || undefined,
        stage: sale.stage || undefined,
        category: sale.category,
        estimated_amount: sale.estimated_amount ?? undefined,
        probability: sale.probability ?? undefined,
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
        `"${sale.name}" 영업을 수주 확정 — 메인 프로젝트로 전환할까요? 노션의 영업 단계는 "완료"로 자동 변경되고 새 프로젝트가 생성됩니다.`,
      )
    )
      return;
    setBusy(true);
    setErr(null);
    try {
      const project = await convertSale(sale.id);
      refreshSales();
      onClose();
      if (typeof window !== "undefined") {
        window.location.href = `/project?id=${project.id}`;
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "수주 전환 실패");
    } finally {
      setBusy(false);
    }
  };

  const handleLinkProject = async (project: Project): Promise<void> => {
    if (!sale) return;
    if (
      !confirm(
        `"${sale.name}" 영업을 기존 프로젝트 "${project.name}"에 연결할까요? 영업 단계는 "완료"로 자동 변경됩니다.`,
      )
    )
      return;
    setBusy(true);
    setErr(null);
    try {
      await linkSaleToProject(sale.id, project.id);
      refreshSales();
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "프로젝트 연결 실패");
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

  // 기존 프로젝트 연결 — 단계 무관, 수주영업이고 미전환이면 가능 (admin)
  const canLink =
    isEdit &&
    isAdmin &&
    sale != null &&
    sale.kind === "수주영업" &&
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

          <Field
            label={
              isEdit
                ? "영업코드 (수정 가능)"
                : "영업코드 (비워두면 자동 부여)"
            }
          >
            <input
              className={inputCls}
              placeholder={isEdit ? "" : "예: 26-영업-001 (자동 부여)"}
              value={form.code ?? ""}
              onChange={(e) => setForm({ ...form, code: e.target.value })}
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

          <div className="grid grid-cols-2 gap-3">
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
            <Field label="수주확률 (%, 0~100)">
              <input
                type="number"
                min={0}
                max={100}
                step={1}
                className={inputCls}
                placeholder="PM 직접 입력"
                value={form.probability ?? ""}
                onChange={(e) =>
                  setForm({
                    ...form,
                    probability: e.target.value
                      ? Number(e.target.value)
                      : undefined,
                  })
                }
              />
            </Field>
          </div>

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
              <span className="ml-1 text-[10px] text-zinc-500">(견적금액 × 수주확률/100)</span>
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
                수주 전환 → 새 프로젝트
              </button>
            )}
            {canLink && (
              <button
                type="button"
                onClick={() => setLinkPickerOpen(true)}
                disabled={busy}
                className="rounded-md border border-emerald-500/40 px-3 py-1.5 text-xs text-emerald-700 hover:bg-emerald-500/10 disabled:opacity-50 dark:text-emerald-400"
              >
                기존 프로젝트 연결
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

      {linkPickerOpen && (
        <ProjectLinkPicker
          onClose={() => setLinkPickerOpen(false)}
          onPick={(project) => {
            setLinkPickerOpen(false);
            void handleLinkProject(project);
          }}
        />
      )}
    </div>
  );
}

function ProjectLinkPicker({
  onClose,
  onPick,
}: {
  onClose: () => void;
  onPick: (project: Project) => void;
}) {
  const [query, setQuery] = useState("");
  const { data, error } = useProjects();

  const projects = data?.items ?? [];
  const q = query.trim().toLowerCase();
  const filtered = (
    q
      ? projects.filter(
          (p) =>
            p.name.toLowerCase().includes(q) ||
            (p.code ?? "").toLowerCase().includes(q),
        )
      : projects.filter((p) => !p.completed)
  )
    .slice()
    // 정렬: 완료 안 된 것 먼저, 그 다음 code 역순(최신 코드부터). 50개 limit 안에서 예측성 확보.
    .sort((a, b) => {
      if (a.completed !== b.completed) return a.completed ? 1 : -1;
      return (b.code ?? "").localeCompare(a.code ?? "");
    });

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-lg border border-zinc-200 bg-white shadow-xl dark:border-zinc-700 dark:bg-zinc-900"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
          <h3 className="text-sm font-semibold">기존 프로젝트 연결</h3>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800"
            aria-label="닫기"
          >
            ×
          </button>
        </header>
        <div className="space-y-2 p-3">
          <input
            type="text"
            placeholder="프로젝트명 또는 CODE 검색"
            className={inputCls}
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <p className="text-[10px] text-zinc-500">
            기본은 진행 중인 프로젝트만 표시. 완료된 프로젝트도 연결하려면 검색어를 입력하세요.
          </p>
          {error && (
            <div className="rounded-md border border-red-500/40 bg-red-500/5 p-2 text-xs text-red-500">
              {error instanceof Error ? error.message : String(error)}
            </div>
          )}
          <div className="max-h-[50vh] overflow-y-auto rounded-md border border-zinc-200 dark:border-zinc-800">
            {filtered.length === 0 ? (
              <p className="p-4 text-center text-xs text-zinc-500">
                {q ? "검색 결과 없음" : "진행 중 프로젝트 없음"}
              </p>
            ) : (
              <ul>
                {filtered.slice(0, 50).map((p) => (
                  <li key={p.id}>
                    <button
                      type="button"
                      onClick={() => onPick(p)}
                      className="block w-full border-b border-zinc-100 px-3 py-2 text-left hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-800/50"
                    >
                      <div className="text-sm font-medium">{p.name}</div>
                      <div className="mt-0.5 text-[11px] text-zinc-500">
                        <span className="font-mono">
                          {p.code || p.id.slice(0, 6)}
                        </span>
                        <span className="ml-2">{p.stage}</span>
                        {p.completed && (
                          <span className="ml-2 text-zinc-400">완료</span>
                        )}
                      </div>
                    </button>
                  </li>
                ))}
                {filtered.length > 50 && (
                  <li className="px-3 py-2 text-[11px] text-zinc-500">
                    상위 50개만 표시 — 검색어로 좁혀주세요
                  </li>
                )}
              </ul>
            )}
          </div>
        </div>
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
