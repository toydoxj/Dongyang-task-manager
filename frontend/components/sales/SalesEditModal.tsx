"use client";

import { useEffect, useRef, useState } from "react";
import { useSWRConfig } from "swr";

import { useAuth } from "@/components/AuthGuard";
import QuoteForm from "@/components/sales/QuoteForm";
import {
  addSaleExternalQuote,
  addSaleQuote,
  archiveSale,
  attachExternalQuotePdf,
  convertSale,
  createSale,
  deleteSaleQuote,
  downloadQuoteBundlePdf,
  downloadQuotePdf,
  linkSaleToProject,
  listSaleQuotes,
  saveQuoteBundlePdfToDrive,
  saveQuotePdfToDrive,
  updateSale,
  updateSaleExternalQuote,
  updateSaleQuote,
} from "@/lib/api";
import {
  BID_STAGES,
  CONVERTIBLE_STAGES,
  type Project,
  type QuoteFormResponse,
  type QuoteInput,
  type QuoteResult,
  type QuoteType,
  type Sale,
  type SaleCreateRequest,
} from "@/lib/domain";
import { useClients, useProjects } from "@/lib/hooks";
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

// 견적서 종류별 산출 default 값 — 사장이 운영하는 xlsx 양식의 표준 요율/조정/절삭
// 단위. 사용자가 종류 select를 변경할 때 자동 적용 (모달 prefill 시에는 미적용 —
// 기존 견적의 사용자 정의 값을 보존).
//   overhead_pct: 제경비 % (직접인건비 대비)
//   tech_fee_pct: 기술료 %  (직접인건비 + 제경비 대비)
//   adjustment_pct: 당사 조정 % (subtotal 대비)
//   truncate_unit: 절삭 단위 (1_000_000 = 백만, 100_000 = 십만)
const QUOTE_TYPE_DEFAULTS: Record<
  QuoteType,
  Pick<QuoteInput, "overhead_pct" | "tech_fee_pct" | "adjustment_pct" | "truncate_unit">
> = {
  구조설계: { overhead_pct: 110, tech_fee_pct: 20, adjustment_pct: 87, truncate_unit: 1_000_000 },
  구조검토: { overhead_pct: 110, tech_fee_pct: 20, adjustment_pct: 87, truncate_unit: 1_000_000 },
  성능기반내진설계: { overhead_pct: 110, tech_fee_pct: 20, adjustment_pct: 87, truncate_unit: 1_000_000 },
  // 정기/정밀점검 (PR-Q5) — xlsx 시특법 sheet 실 사례 조정률·절삭
  정기안전점검: { overhead_pct: 110, tech_fee_pct: 20, adjustment_pct: 27, truncate_unit: 100_000 },
  정밀점검: { overhead_pct: 110, tech_fee_pct: 20, adjustment_pct: 88, truncate_unit: 1_000_000 },
  // 정밀안전진단 (PR-Q6) — xlsx 시특법 F11=1, overhead 120%·tech 40%·조정 45%
  정밀안전진단: { overhead_pct: 120, tech_fee_pct: 40, adjustment_pct: 45, truncate_unit: 1_000_000 },
  // 건축물관리법점검 (PR-Q4) — xlsx 90% × 십만 절삭
  건축물관리법점검: { overhead_pct: 110, tech_fee_pct: 20, adjustment_pct: 90, truncate_unit: 100_000 },
  // 내진성능평가 (PR-Q8) — xlsx 실 사례 (서울대 치과병원) 조정 45%
  내진성능평가: { overhead_pct: 110, tech_fee_pct: 20, adjustment_pct: 45, truncate_unit: 1_000_000 },
  // 내진평가 패키지 부속 — xlsx 두 페이지 (보강설계+3자검토+기술감리, 합계 절삭 십만)
  내진보강설계: { overhead_pct: 110, tech_fee_pct: 20, adjustment_pct: 87, truncate_unit: 100_000 },
  "3자검토": { overhead_pct: 110, tech_fee_pct: 20, adjustment_pct: 87, truncate_unit: 100_000 },
  // 구조감리 (PR-Q3) — tech 30, 사장 운영 조정률 55%
  구조감리: { overhead_pct: 110, tech_fee_pct: 30, adjustment_pct: 55, truncate_unit: 1_000_000 },
  // 현장기술지원 (PR-Q2) — xlsx 80% 조정
  현장기술지원: { overhead_pct: 110, tech_fee_pct: 20, adjustment_pct: 80, truncate_unit: 1_000_000 },
  기타: { overhead_pct: 110, tech_fee_pct: 20, adjustment_pct: 87, truncate_unit: 1_000_000 },
};

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
  // 발주처(의뢰처) 자동완성 입력 — ProjectCreateModal과 동일 패턴.
  // form.client_id에는 매칭 성공 시 client.id, 미매칭/빈값이면 ""로 동기화.
  // clientUserEdited: 사용자가 입력란을 직접 건드렸을 때만 form.client_id를 덮어씀.
  // (clientsData에 기존 client_id가 빠져 있어도 무심코 relation이 해제되는 회귀 차단)
  const [client, setClient] = useState("");
  const [clientUserEdited, setClientUserEdited] = useState(false);
  // 탭 시스템 — 수정 모드도 quote_form_data가 있으면 견적서 탭 활성 (수정/재제출)
  const [activeTab, setActiveTab] = useState<"info" | "quote">("info");
  const [quoteInput, setQuoteInput] = useState<QuoteInput>({
    type_rate: 1.0,
    structure_rate: 1.0,
    coefficient: 1.0,
    adjustment_pct: 87,
    printing_fee: 500_000,
  });
  const [quoteResult, setQuoteResult] = useState<QuoteResult | null>(null);

  // 영업당 다중 견적 (PR-M3) — 모달 열릴 때 listSaleQuotes로 fetch.
  // quoteMode: list = 견적 N개 row 표시, new = 신규 작성 form, edit = 기존 수정 form.
  const [quoteList, setQuoteList] = useState<QuoteFormResponse[]>([]);
  const [quoteMode, setQuoteMode] = useState<"list" | "new" | "edit">("list");
  const [editingQuoteId, setEditingQuoteId] = useState<string | null>(null);
  // 외부 견적 inline form (PR-EXT) — 산출 X, service + amount만.
  const [externalFormOpen, setExternalFormOpen] = useState(false);
  const [externalDraft, setExternalDraft] = useState({ service: "", amount: 0 });
  const [editingExternalId, setEditingExternalId] = useState<string | null>(null);

  // 종류별 default 자동 적용 — useRef로 prev type 추적해 모달 첫 prefill 시에는
  // skip (기존 견적의 사용자 정의 값을 보존), 사용자가 select 변경할 때만 reset.
  const prevQuoteTypeRef = useRef<QuoteType | undefined>(undefined);

  const open = sale != null || openNew;
  const isEdit = sale != null;

  // 발주처 자동완성 데이터 — 모달 열릴 때만 fetch.
  const { data: clientsData } = useClients(open);
  // 묶음 PDF는 영업 1건 안 견적 N개 모델로 변경 (PR-M4a). parent_lead_id grouping
  // 폐기 — quoteList.length > 1 일 때만 묶음 PDF 버튼 노출.
  const hasMultipleQuotes = quoteList.length > 1;
  const normName = (s: string): string => s.trim().toLowerCase();
  const clientMatch =
    client.trim() === ""
      ? undefined
      : clientsData?.items.find((c) => normName(c.name) === normName(client));

  useEffect(() => {
    if (!open) return;
    setErr(null);
    setClientUserEdited(false);
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
        assignees: sale.assignees,
        quote_type: sale.quote_type || undefined,
      });
      // 견적서 데이터가 있으면 prefill — 수정/재제출 시나리오
      if (sale.quote_form_data?.input) {
        // 영업 정보 row의 규모 4종이 견적서 입력보다 최신일 수 있어 우선 적용
        setQuoteInput({
          ...sale.quote_form_data.input,
          gross_floor_area:
            sale.gross_floor_area ?? sale.quote_form_data.input.gross_floor_area,
          floors_above:
            sale.floors_above ?? sale.quote_form_data.input.floors_above,
          floors_below:
            sale.floors_below ?? sale.quote_form_data.input.floors_below,
          building_count:
            sale.building_count ?? sale.quote_form_data.input.building_count,
        });
        setQuoteResult(sale.quote_form_data.result ?? null);
      } else {
        // 견적서 없는 영업도 영업 정보의 규모는 prefill — 견적서 새로 작성 시 활용
        setQuoteInput({
          type_rate: 1.0,
          structure_rate: 1.0,
          coefficient: 1.0,
          adjustment_pct: 87,
          printing_fee: 500_000,
          gross_floor_area: sale.gross_floor_area ?? undefined,
          floors_above: sale.floors_above ?? null,
          floors_below: sale.floors_below ?? null,
          building_count: sale.building_count ?? null,
        });
        setQuoteResult(null);
      }
      setActiveTab("info");
    } else {
      setForm({
        name: "",
        kind: "수주영업",
        stage: "준비",
        assignees: defaultAssignee ? [defaultAssignee] : [],
      });
      setClient("");
      setActiveTab("info");
      setQuoteInput({
        type_rate: 1.0,
        structure_rate: 1.0,
        coefficient: 1.0,
        adjustment_pct: 87,
        printing_fee: 500_000,
      });
      setQuoteResult(null);
    }
  }, [open, sale, defaultAssignee]);

  // 수정 모드: clientsData 도착 시 sale.client_id로 name lookup → 발주처 input 채움.
  // sale 로딩 useEffect와 분리한 이유 — clientsData가 늦게 도착해도 form 전체가 reset되지 않게.
  useEffect(() => {
    if (!open || !sale || clientsData == null) return;
    if (!sale.client_id) {
      setClient("");
      return;
    }
    const found = clientsData.items.find((c) => c.id === sale.client_id);
    setClient(found?.name ?? "");
  }, [open, sale, clientsData]);

  // client 입력 → form.client_id 동기화. 사용자가 입력란을 직접 변경한 경우에만 작동.
  // (기존 sale.client_id가 clientsData 누락으로 lookup 실패해도 relation이 무심코 해제되지 않게)
  useEffect(() => {
    if (clientsData == null || !clientUserEdited) return;
    const id = clientMatch?.id ?? "";
    setForm((f) => (f.client_id === id ? f : { ...f, client_id: id }));
  }, [clientMatch, clientsData, clientUserEdited]);

  // 발주처(client) → 견적서 수신처(recipient_company) 자동 동기화.
  // 사용자가 견적서 폼에서 수신처를 직접 편집한 경우에도 발주처를 다시 변경하지 않으면
  // 덮어쓰지 않음. 발주처 != 수신처인 케이스는 실무상 없다는 결정에 따라 단순 동기화.
  useEffect(() => {
    setQuoteInput((prev) =>
      prev.recipient_company === client
        ? prev
        : { ...prev, recipient_company: client },
    );
  }, [client]);

  // 영업정보 탭의 핵심 필드 → 견적서 quoteInput 자동 echo.
  // 견적서 탭은 read-only로 표시 (영업정보에서만 입력).
  useEffect(() => {
    setQuoteInput((prev) => ({
      ...prev,
      service_name: form.name ?? prev.service_name,
      gross_floor_area: form.gross_floor_area ?? prev.gross_floor_area,
      floors_above: form.floors_above ?? prev.floors_above,
      floors_below: form.floors_below ?? prev.floors_below,
      building_count: form.building_count ?? prev.building_count,
    }));
  }, [
    form.name,
    form.gross_floor_area,
    form.floors_above,
    form.floors_below,
    form.building_count,
  ]);

  // 모달 닫힘 시 prev type 추적 ref 초기화 — 다음 모달 열림 시 첫 prefill을 skip
  // 시점으로 처리하기 위함.
  useEffect(() => {
    if (!open) prevQuoteTypeRef.current = undefined;
  }, [open]);

  // 견적 list fetch — 신규/수정 모두 모달 열릴 때 list 모드로 시작.
  // 신규 영업: 빈 list + "+ 신규 견적" → createSale flow. 수정: backend list fetch.
  useEffect(() => {
    if (!open) {
      setQuoteList([]);
      setQuoteMode("list");
      setEditingQuoteId(null);
      return;
    }
    setEditingQuoteId(null);
    setQuoteMode("list");
    if (!sale) {
      setQuoteList([]);
      return;
    }
    listSaleQuotes(sale.id)
      .then((qs) => setQuoteList(qs))
      .catch((e) => {
        // eslint-disable-next-line no-console
        console.error("견적 list fetch:", e);
      });
  }, [open, sale]);

  // 견적 list 새로고침 helper
  const refreshQuoteList = async (): Promise<void> => {
    if (!sale) return;
    try {
      const qs = await listSaleQuotes(sale.id);
      setQuoteList(qs);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "견적 list 갱신 실패");
    }
  };

  // 종류 변경 시 산출 default 자동 적용 (overhead/tech/adj/truncate).
  // 모달 첫 prefill (prev=undefined → next=type)은 skip — 기존 견적의 사용자
  // 정의 값을 보존. quoteInput.quote_type은 QuoteForm의 종류 select가 set.
  useEffect(() => {
    const next = quoteInput.quote_type as QuoteType | undefined;
    const prev = prevQuoteTypeRef.current;
    if (prev !== undefined && prev !== next && next) {
      const def = QUOTE_TYPE_DEFAULTS[next];
      if (def) {
        setQuoteInput((q) => ({ ...q, ...def }));
      }
    }
    prevQuoteTypeRef.current = next;
  }, [quoteInput.quote_type]);

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
    // 견적서 탭 저장 (PR-M3) — list 모드는 저장 X (신규/수정 공통).
    // new 모드: 신규 영업이면 createSale, 영업 수정이면 addSaleQuote.
    // edit 모드: updateSaleQuote.
    if (activeTab === "quote") {
      if (quoteMode === "list") {
        setErr(
          "list 모드에서는 저장할 견적이 없습니다 — 견적 row의 [편집] 또는 [+ 신규 견적]을 사용하세요.",
        );
        return;
      }
      if (!quoteInput.service_name?.trim()) {
        setErr("용역명은 필수입니다.");
        return;
      }
      if (!quoteInput.gross_floor_area || quoteInput.gross_floor_area <= 0) {
        setErr("연면적을 입력해야 산출이 됩니다.");
        return;
      }
      if (!quoteResult) {
        setErr("산출 결과가 아직 준비되지 않았습니다. 잠시 후 다시 시도하세요.");
        return;
      }
      const recipientMatch = quoteInput.recipient_company
        ? clientsData?.items.find(
            (c) =>
              c.name.trim().toLowerCase() ===
              (quoteInput.recipient_company ?? "").trim().toLowerCase(),
          )
        : undefined;
      const resolvedClientId = form.client_id || recipientMatch?.id;

      const scaleFields = {
        gross_floor_area: quoteInput.gross_floor_area,
        floors_above: quoteInput.floors_above ?? undefined,
        floors_below: quoteInput.floors_below ?? undefined,
        building_count: quoteInput.building_count ?? undefined,
        quote_type: quoteInput.quote_type ?? undefined,
      };

      setBusy(true);
      setErr(null);
      try {
        if (!isEdit) {
          // 신규 영업 + 첫 견적 동시 저장 (legacy 흐름 유지). 단일 schema는
          // backend normalize_quote_forms가 list[0]으로 자동 wrap.
          const body: SaleCreateRequest = {
            name: quoteInput.service_name,
            kind: "수주영업",
            stage: "준비",
            estimated_amount: quoteResult.final,
            client_id: resolvedClientId,
            assignees: defaultAssignee ? [defaultAssignee] : [],
            ...scaleFields,
            quote_form_data: { input: quoteInput, result: quoteResult },
          };
          await createSale(body);
          refreshSales();
          onClose();
        } else if (sale && quoteMode === "new") {
          // 영업 수정 모드 + 신규 견적 추가
          await addSaleQuote(sale.id, quoteInput);
          await refreshQuoteList();
          setQuoteMode("list");
          refreshSales();
          alert("견적이 추가되었습니다.");
        } else if (sale && quoteMode === "edit" && editingQuoteId) {
          await updateSaleQuote(sale.id, editingQuoteId, quoteInput);
          await refreshQuoteList();
          setQuoteMode("list");
          setEditingQuoteId(null);
          refreshSales();
          alert("견적이 수정되었습니다.");
        }
      } catch (e) {
        setErr(e instanceof Error ? e.message : "저장 실패");
      } finally {
        setBusy(false);
      }
      return;
    }

    // 영업 정보 탭 저장 — quote_form_data는 건드리지 않음 (form에 미포함).
    // backend update_sale은 quote_form_data가 None이면 변경 안 함.
    if (!form.name?.trim()) {
      setErr("용역명은 필수입니다.");
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
    if (!confirm(`"${sale.name}" 영업 건을 삭제할까요?`)) return;
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
    sale != null &&
    sale.kind === "수주영업" &&
    CONVERTIBLE_STAGES.includes(sale.stage) &&
    !sale.converted_project_id;

  // 기존 프로젝트 연결 — 단계 무관, 수주영업이고 미전환이면 가능 (전 직원)
  const canLink =
    isEdit &&
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
        className="w-full max-w-4xl rounded-lg border border-zinc-200 bg-white shadow-xl dark:border-zinc-700 dark:bg-zinc-900"
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

        <div className="flex border-b border-zinc-200 px-4 dark:border-zinc-800">
          <TabButton
            active={activeTab === "info"}
            onClick={() => setActiveTab("info")}
          >
            영업 정보
          </TabButton>
          <TabButton
            active={activeTab === "quote"}
            onClick={() => setActiveTab("quote")}
          >
            {isEdit && sale?.quote_form_data?.input
              ? "견적서 수정"
              : "견적서 작성"}
          </TabButton>
        </div>

        <div className="max-h-[70vh] space-y-3 overflow-y-auto px-4 py-3">
          {err && (
            <div className="rounded-md border border-red-500/40 bg-red-500/5 p-2 text-xs text-red-500">
              {err}
            </div>
          )}

          {activeTab === "quote" ? (
            quoteMode === "list" ? (
              // PR-M3 List view — 영업당 견적 N개 표시 + PR-EXT 외부 견적
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-medium">
                    견적서 ({quoteList.length}건)
                  </h3>
                  <div className="flex gap-1">
                  <button
                    type="button"
                    disabled={!sale}
                    onClick={() => {
                      if (!sale) return;
                      setExternalDraft({ service: "", amount: 0 });
                      setEditingExternalId(null);
                      setExternalFormOpen(true);
                    }}
                    className="rounded-md border border-amber-600/40 bg-amber-500/10 px-3 py-1.5 text-xs font-medium text-amber-700 hover:bg-amber-500/20 disabled:opacity-50 dark:text-amber-400"
                    title={sale ? "외주사 견적 (산출 X, 갑지 row만)" : "영업 저장 후 사용 가능"}
                  >
                    + 외부 견적
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      // 새 견적: input default reset (단가 등급/조정 등은 그대로).
                      // 발주처(client) + 영업 정보의 규모 4종은 기존 견적과 무관하게
                      // 영업 row에서 echo — 두 번째 이후 견적도 동일 영업의 발주처/규모 자동 채움.
                      // 구조설계 default 직접경비: 인쇄비 50만원 + 지불방법 "쌍방의 협의에 의함."
                      setQuoteInput({
                        type_rate: 1.0,
                        structure_rate: 1.0,
                        coefficient: 1.0,
                        adjustment_pct: 87,
                        printing_fee: 500_000,
                        direct_expense_items: [
                          { name: "인쇄비", amount: 500_000 },
                        ],
                        gross_floor_area: form.gross_floor_area ?? undefined,
                        floors_above: form.floors_above ?? null,
                        floors_below: form.floors_below ?? null,
                        building_count: form.building_count ?? null,
                        service_name: form.name ?? "",
                        quote_type: "구조설계",
                        recipient_company: client,
                        payment_terms: "쌍방의 협의에 의함.",
                      });
                      setQuoteResult(null);
                      setEditingQuoteId(null);
                      setQuoteMode("new");
                    }}
                    className="rounded-md border border-emerald-700/40 bg-emerald-600/10 px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-600/20 dark:text-emerald-400"
                  >
                    + 신규 견적
                  </button>
                  </div>
                </div>

                {externalFormOpen && (
                  <div className="space-y-2 rounded-md border border-amber-300 bg-amber-50/40 p-3 dark:border-amber-600/40 dark:bg-amber-900/10">
                    <div className="text-xs font-medium text-amber-700 dark:text-amber-400">
                      외부 견적 {editingExternalId ? "수정" : "추가"}
                    </div>
                    <input
                      type="text"
                      placeholder="업무내용 (예: 구조진단 외주 (B사))"
                      value={externalDraft.service}
                      onChange={(e) =>
                        setExternalDraft({
                          ...externalDraft,
                          service: e.target.value,
                        })
                      }
                      className={inputCls}
                    />
                    <input
                      type="number"
                      min={0}
                      placeholder="금액 (원)"
                      value={externalDraft.amount || ""}
                      onChange={(e) =>
                        setExternalDraft({
                          ...externalDraft,
                          amount: e.target.value ? Number(e.target.value) : 0,
                        })
                      }
                      className={inputCls}
                    />
                    <div className="flex justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          setExternalFormOpen(false);
                          setEditingExternalId(null);
                          setExternalDraft({ service: "", amount: 0 });
                        }}
                        className="rounded border border-zinc-300 px-2 py-1 text-[11px] hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
                      >
                        취소
                      </button>
                      <button
                        type="button"
                        disabled={busy || !externalDraft.service.trim()}
                        onClick={async () => {
                          if (!sale) return;
                          setBusy(true);
                          setErr(null);
                          try {
                            if (editingExternalId) {
                              await updateSaleExternalQuote(
                                sale.id,
                                editingExternalId,
                                externalDraft,
                              );
                            } else {
                              await addSaleExternalQuote(sale.id, externalDraft);
                            }
                            await refreshQuoteList();
                            setExternalFormOpen(false);
                            setEditingExternalId(null);
                            setExternalDraft({ service: "", amount: 0 });
                          } catch (e) {
                            setErr(e instanceof Error ? e.message : "외부 견적 저장 실패");
                          } finally {
                            setBusy(false);
                          }
                        }}
                        className="rounded border border-amber-600/40 bg-amber-500/20 px-2 py-1 text-[11px] font-medium text-amber-700 hover:bg-amber-500/30 disabled:opacity-50 dark:text-amber-400"
                      >
                        {editingExternalId ? "수정" : "추가"}
                      </button>
                    </div>
                  </div>
                )}

                {quoteList.length === 0 ? (
                  <p className="rounded-md border border-dashed border-zinc-300 px-3 py-4 text-center text-xs text-zinc-500 dark:border-zinc-700">
                    아직 견적 없음. "+ 신규 견적"으로 작성하세요.
                  </p>
                ) : (
                  <ul className="space-y-1">
                    {quoteList.map((q) => (
                      <li
                        key={q.id}
                        className={cn(
                          "rounded border px-3 py-2",
                          q.is_external
                            ? "border-amber-300 bg-amber-50/40 dark:border-amber-600/40 dark:bg-amber-900/10"
                            : "border-zinc-200 dark:border-zinc-800",
                        )}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex-1 min-w-0">
                            <div className="text-sm font-medium">
                              {q.is_external ? (
                                <>
                                  <span className="mr-1 inline-block rounded bg-amber-500 px-1.5 py-0.5 text-[9px] font-semibold text-white">
                                    외부
                                  </span>
                                  {q.service || "외부 견적"}
                                </>
                              ) : (
                                <>
                                  {q.full_doc || "—"} ·{" "}
                                  {q.input.quote_type ?? "구조설계"}
                                </>
                              )}
                            </div>
                            <div className="truncate text-xs text-zinc-500">
                              {q.is_external
                                ? `₩${(q.amount ?? 0).toLocaleString()}`
                                : `${q.input.service_name ?? "—"} · ₩${(q.result.final ?? 0).toLocaleString()}`}
                            </div>
                            {q.is_external && q.attached_pdf_name && (
                              <div className="mt-0.5 truncate text-[10px] text-amber-700 dark:text-amber-400">
                                📎 {q.attached_pdf_name}
                              </div>
                            )}
                            {!q.is_external &&
                              (() => {
                                const items = (
                                  q.input.direct_expense_items ?? []
                                ).filter((it) => (it.amount ?? 0) > 0);
                                if (items.length === 0) return null;
                                return (
                                  <ul className="mt-1 space-y-0.5 pl-2 text-[10px] text-zinc-500 dark:text-zinc-400">
                                    {items.map((it, i) => (
                                      <li key={i}>
                                        └ {it.name || "항목명 없음"} ·{" "}
                                        ₩{(it.amount ?? 0).toLocaleString()}
                                      </li>
                                    ))}
                                  </ul>
                                );
                              })()}
                          </div>
                          <div className="flex shrink-0 gap-1">
                            {q.is_external ? (
                              <>
                                <button
                                  type="button"
                                  onClick={() => {
                                    setExternalDraft({
                                      service: q.service ?? "",
                                      amount: q.amount ?? 0,
                                    });
                                    setEditingExternalId(q.id);
                                    setExternalFormOpen(true);
                                  }}
                                  className="rounded border border-zinc-300 px-2 py-1 text-[11px] hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
                                >
                                  편집
                                </button>
                                <label
                                  className={cn(
                                    "cursor-pointer rounded border border-amber-600/40 px-2 py-1 text-[11px] text-amber-700 hover:bg-amber-500/10 dark:text-amber-400",
                                    busy && "opacity-50",
                                  )}
                                >
                                  {q.attached_pdf_url ? "재첨부" : "PDF 첨부"}
                                  <input
                                    type="file"
                                    accept="application/pdf"
                                    className="hidden"
                                    disabled={busy}
                                    onChange={async (e) => {
                                      const f = e.target.files?.[0];
                                      e.target.value = "";
                                      if (!f || !sale) return;
                                      setBusy(true);
                                      setErr(null);
                                      try {
                                        await attachExternalQuotePdf(
                                          sale.id,
                                          q.id,
                                          f,
                                        );
                                        await refreshQuoteList();
                                        refreshSales();
                                        alert("PDF 첨부 완료");
                                      } catch (err2) {
                                        setErr(
                                          err2 instanceof Error
                                            ? err2.message
                                            : "PDF 첨부 실패",
                                        );
                                      } finally {
                                        setBusy(false);
                                      }
                                    }}
                                  />
                                </label>
                                {q.attached_pdf_url && (
                                  <a
                                    href={q.attached_pdf_url}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="rounded border border-emerald-700/40 px-2 py-1 text-[11px] text-emerald-700 hover:bg-emerald-600/10 dark:text-emerald-400"
                                  >
                                    보기
                                  </a>
                                )}
                              </>
                            ) : (
                              <>
                                <button
                                  type="button"
                                  onClick={() => {
                                    setQuoteInput(q.input);
                                    setQuoteResult(q.result);
                                    setEditingQuoteId(q.id);
                                    setQuoteMode("edit");
                                  }}
                                  className="rounded border border-zinc-300 px-2 py-1 text-[11px] hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
                                >
                                  편집
                                </button>
                                <button
                                  type="button"
                                  onClick={() => {
                                    if (!sale) return;
                                    void downloadQuotePdf(sale.id, q.id).catch(
                                      (e) =>
                                        setErr(
                                          e instanceof Error
                                            ? e.message
                                            : "PDF 다운로드 실패",
                                        ),
                                    );
                                  }}
                                  className="rounded border border-emerald-700/40 px-2 py-1 text-[11px] text-emerald-700 hover:bg-emerald-600/10 dark:text-emerald-400"
                                >
                                  PDF
                                </button>
                                <button
                                  type="button"
                                  onClick={async () => {
                                    if (!sale) return;
                                    setBusy(true);
                                    setErr(null);
                                    try {
                                      await saveQuotePdfToDrive(sale.id, q.id);
                                      refreshSales();
                                      alert("Drive 저장 완료");
                                    } catch (e) {
                                      setErr(
                                        e instanceof Error
                                          ? e.message
                                          : "PDF 저장 실패",
                                      );
                                    } finally {
                                      setBusy(false);
                                    }
                                  }}
                                  disabled={busy}
                                  className="rounded border border-blue-500/40 px-2 py-1 text-[11px] text-blue-700 hover:bg-blue-500/10 disabled:opacity-50 dark:text-blue-400"
                                >
                                  저장
                                </button>
                              </>
                            )}
                            <button
                              type="button"
                              onClick={async () => {
                                if (!sale) return;
                                const label = q.is_external
                                  ? `외부 견적 [${q.service}]`
                                  : `견적 [${q.full_doc}]`;
                                if (
                                  !confirm(
                                    `${label}을 삭제하시겠습니까?\n(파일은 보존, 노션 row만 갱신)`,
                                  )
                                )
                                  return;
                                setBusy(true);
                                setErr(null);
                                try {
                                  await deleteSaleQuote(sale.id, q.id);
                                  await refreshQuoteList();
                                  refreshSales();
                                } catch (e) {
                                  setErr(
                                    e instanceof Error
                                      ? e.message
                                      : "삭제 실패",
                                  );
                                } finally {
                                  setBusy(false);
                                }
                              }}
                              disabled={busy}
                              className="rounded border border-red-500/40 px-2 py-1 text-[11px] text-red-600 hover:bg-red-500/10 disabled:opacity-50 dark:text-red-400"
                            >
                              삭제
                            </button>
                          </div>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ) : (
              // PR-M3 New/Edit form view
              <>
                <button
                  type="button"
                  onClick={() => {
                    setQuoteMode("list");
                    setEditingQuoteId(null);
                  }}
                  className="text-xs text-blue-600 hover:underline dark:text-blue-400"
                >
                  ← 견적 목록
                </button>
                <p className="rounded-md border border-blue-500/30 bg-blue-500/5 px-3 py-2 text-[11px] text-blue-700 dark:text-blue-400">
                  {!isEdit
                    ? "저장하면 영업 건이 자동 생성되고 첫 견적이 함께 등록됩니다 (영업코드·문서번호 자동 부여, 단계 = 준비). 추가 견적은 영업 저장 후 list view에서 작성."
                    : quoteMode === "edit"
                      ? "기존 견적 수정 — doc_number/suffix는 보존됩니다."
                      : "신규 견적 추가 — 분류별 sequence + suffix(A/B/C) 자동 부여."}
                </p>
                <QuoteForm
                  value={quoteInput}
                  onChange={setQuoteInput}
                  onResultChange={setQuoteResult}
                  echoReadOnly
                />
              </>
            )
          ) : (
            <>
          <Field label="용역명">
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

          <Field label="발주처">
            <input
              type="text"
              list="dy-clients-sales"
              value={client}
              onChange={(e) => {
                setClient(e.target.value);
                setClientUserEdited(true);
              }}
              className={inputCls}
              placeholder={
                clientsData
                  ? `목록 ${clientsData.count}개 자동완성`
                  : "발주처 목록 불러오는 중..."
              }
            />
            <datalist id="dy-clients-sales">
              {clientsData?.items.map((c) => (
                <option key={c.id} value={c.name}>
                  {c.category}
                </option>
              ))}
            </datalist>
            {client.trim() !== "" && !clientMatch && (
              <p className="mt-1 text-[10px] text-zinc-500">
                미등록 발주처 — /admin/incomes/clients 에서 먼저 등록 후 선택하세요. (현재 입력은 저장되지 않습니다)
              </p>
            )}
            {clientMatch && (
              <p className="mt-1 text-[10px] text-emerald-500">
                ✓ 매칭: {clientMatch.name}
                {clientMatch.category ? ` (${clientMatch.category})` : ""}
              </p>
            )}
          </Field>

          <Field label="위치">
            <input
              className={inputCls}
              value={quoteInput.location ?? ""}
              onChange={(e) =>
                setQuoteInput((q) => ({ ...q, location: e.target.value }))
              }
              placeholder="예: 경기 고양시 일산서구"
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
            </>
          )}
        </div>

        <footer className="flex items-center justify-between gap-2 border-t border-zinc-200 px-4 py-3 dark:border-zinc-800">
          <div className="flex gap-2">
            {isEdit && sale && sale.quote_doc_number && (
              <>
                {hasMultipleQuotes && (
                  <>
                    <button
                      type="button"
                      onClick={() => {
                        void downloadQuoteBundlePdf(sale.id).catch((e) =>
                          setErr(
                            e instanceof Error
                              ? e.message
                              : "묶음 PDF 다운로드 실패",
                          ),
                        );
                      }}
                      disabled={busy}
                      className="rounded-md border border-amber-600/40 bg-amber-500/10 px-3 py-1.5 text-xs font-medium text-amber-700 hover:bg-amber-500/20 disabled:opacity-50 dark:text-amber-400"
                      title="영업 내 모든 견적을 1 PDF로 묶어 다운로드"
                    >
                      묶음 PDF 다운로드
                    </button>
                    <button
                      type="button"
                      onClick={async () => {
                        setBusy(true);
                        setErr(null);
                        try {
                          await saveQuoteBundlePdfToDrive(sale.id);
                          refreshSales();
                          alert(
                            "WORKS Drive [견적서]/" +
                              new Date().getFullYear() +
                              "년 폴더에 통합 PDF가 저장되었습니다.",
                          );
                        } catch (e) {
                          setErr(
                            e instanceof Error ? e.message : "묶음 PDF 저장 실패",
                          );
                        } finally {
                          setBusy(false);
                        }
                      }}
                      disabled={busy}
                      className="rounded-md border border-amber-700/40 px-3 py-1.5 text-xs text-amber-700 hover:bg-amber-500/10 disabled:opacity-50 dark:text-amber-400"
                      title="통합 PDF를 WORKS Drive에 저장하고 노션 통합견적서첨부 컬럼에 url 등록"
                    >
                      묶음 PDF 저장
                    </button>
                  </>
                )}
              </>
            )}
            {isEdit && (
              <button
                type="button"
                onClick={handleDelete}
                disabled={busy}
                className="rounded-md border border-red-500/40 px-3 py-1.5 text-xs text-red-500 hover:bg-red-500/10 disabled:opacity-50"
              >
                삭제
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
              {busy
                ? "저장 중…"
                : activeTab === "quote"
                  ? "견적서 저장"
                  : isEdit
                    ? "영업 저장"
                    : "영업 등록"}
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

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        active
          ? "border-b-2 border-zinc-900 px-4 py-2 text-sm font-medium text-zinc-900 dark:border-zinc-100 dark:text-zinc-100"
          : "px-4 py-2 text-sm text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-300"
      }
    >
      {children}
    </button>
  );
}
