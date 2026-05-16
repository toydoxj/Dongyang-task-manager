"""건축물관리법점검 / 시특법(정기·정밀·정밀안전진단) strategy.

PR-DF (Phase 4-J 16단계): quote_calculator/__init__.py에서 분리.

두 strategy를 한 짝으로 묶음 — bma는 건축물관리법(별표 1·3 + 제37·38조),
legal은 시특법(별표 22·23·25·26 + 제61·62조). 둘 다 보간 helper(bma_table /
inspection_legal_table)에 의존하며, BMA는 _calculate_inspection_bma 단독,
legal은 정기점검·정밀점검·정밀안전진단 3종 dispatch가 모두 _calculate_inspection_legal
하나로 위임.

helper(_excel_round_half_up / _resolve_rate) + model(QuoteInput / QuoteResult /
QuoteType / OptionalTaskBreakdown / ManhourFormulaStep)은 __init__.py에 그대로
두고 import. __init__.py가 _DISPATCH 정의 직전에 본 모듈을 import하므로 partial
loading 시점에 attribute가 모두 확보된 상태 → 순환 import 충돌 없음 (PR-DE
struct.py에서 이미 검증된 패턴).
"""
from __future__ import annotations

from app.services.quote_calculator import (
    ManhourFormulaStep,
    OptionalTaskBreakdown,
    QuoteInput,
    QuoteResult,
    QuoteType,
    _excel_round_half_up,
    _resolve_rate,
)


def _calculate_inspection_bma(inp: QuoteInput) -> QuoteResult:
    """건축물관리법점검 strategy (PR-Q4 + PR-Q4b 자동 산정).

    PR-Q4b 자동 산정 분기 (사장 운영 산정표 기반)
    --------------------------------------------
    inp.bma_inspection_type가 "정기" 또는 "정기+구조"이고 gross_floor_area>0,
    building_usage가 BMA_USAGE_FACTORS 키이면 별표 1 보간 + 별표 3 보정 +
    제37조 군집 + 제38조 추가 보정 자동.

    산식 (산정표 B25)
    - 직접인건비 = INT(책임자×기술사) + INT(점검자×초급)
    - 제경비    = INT(직접인건비 × 1.10)              (제34조)
    - 기술료    = INT((직접인건비+제경비) × 0.20)       (제35조)
    - 직접경비  = 100,000원 (제36조 일괄)
    - 소계      = 직접인건비+제경비+기술료+직접경비
    - 업무대가  = 소계 × 경과조정 × 용도조정
                  × (0.8 if 구조생략) × (0.9 if 급수생략)
                  + 선택과업비

    수동 fallback — bma_inspection_type 빈 값이면 기존 PR-Q4 흐름
    (inspection_responsible_days/inspector_days 직접 입력).

    xlsx 검증 (책임자 1.44, 점검자 0.44, 직접경비 100,000, 조정 90%):
    - 직접인건비 = INT(456237×1.44) + INT(235459×0.44) = 656,981 + 103,601 = 760,582
    - 제경비    = INT(760,582 × 1.1)            = 836,640
    - 기술료    = INT((760,582+836,640) × 0.2)   = 319,444
    - 합계      = 760,582+836,640+319,444+100,000 = 2,016,666
    - 조정      = 2,016,666 × 0.9                = 1,814,999.4
    - 절삭(10만) = 14,999
    - 최종      = 1,800,000 (xlsx F23)
    """
    from app.services.bma_table import (
        BMA_USAGE_FACTORS,
        DIRECT_EXPENSE_FIXED,
        INSPECTOR_RATE_DEFAULT,
        RESPONSIBLE_RATE_DEFAULT,
        apply_bma_facility_form,
        bma_aging_factor,
        interpolate_inspector_persons,
        interpolate_responsible_persons,
    )

    # 자동 산정 트리거 — 종류·면적·용도 모두 채워졌을 때만.
    auto_mode = (
        inp.bma_inspection_type in ("정기", "정기+구조")
        and inp.gross_floor_area > 0
        and inp.building_usage in BMA_USAGE_FACTORS
    )

    # 매 단계 INT() — xlsx 수식과 동일한 정수 누적 (truncation 보존).
    # 사장 운영 산정표 default: 책임자 = 기술사(특급기술자) 노임 456,237원,
    # 점검자 = 초급기술자 235,459원 (xlsx M8/M9 명시). backend
    # ENGINEERING_RATES_BY_GRADE["기술사"]는 다른 연도(467,217) — 운영 단가
    # 우선 적용. 사용자가 등급 select 변경 시 dict 단가 사용.
    responsible_rate = (
        _resolve_rate(inp.bma_responsible_grade, "기술사")
        if inp.bma_responsible_grade
        else RESPONSIBLE_RATE_DEFAULT
    )
    inspector_rate = (
        _resolve_rate(inp.bma_inspector_grade, "초급기술자")
        if inp.bma_inspector_grade
        else INSPECTOR_RATE_DEFAULT
    )

    manhours_formula: list[ManhourFormulaStep] = []
    direct_expense_breakdown: list[OptionalTaskBreakdown] = []
    optional_tasks: list[OptionalTaskBreakdown] = []

    if auto_mode:
        structural_extra = inp.bma_inspection_type == "정기+구조"
        # ── Step 1: 별표 1 보간 (책임자/점검자 분리) ────────
        base_responsible = interpolate_responsible_persons(
            inp.gross_floor_area, structural_extra
        )
        base_inspector = interpolate_inspector_persons(inp.gross_floor_area)

        # ── Step 2: 제37조 군집건축물 합산 ──────────────────
        ftype = inp.facility_type or "기본"
        if ftype != "기본" and inp.sub_facility_areas:
            base_responsible_adj = apply_bma_facility_form(
                base_responsible, ftype, inp.sub_facility_areas,
                lambda a: interpolate_responsible_persons(a, structural_extra),
            )
            base_inspector_adj = apply_bma_facility_form(
                base_inspector, ftype, inp.sub_facility_areas,
                interpolate_inspector_persons,
            )
        else:
            base_responsible_adj = base_responsible
            base_inspector_adj = base_inspector

        responsible = base_responsible_adj
        inspector = base_inspector_adj

        # ── Step 3: 별표 3 보정비계 (소계에 곱) ─────────────
        # 경과년수 — completion_year 우선 (KST 기준 자동 계산), 없으면 aging_years
        if inp.completion_year:
            from datetime import datetime, timedelta, timezone
            _kst = timezone(timedelta(hours=9))
            effective_aging = max(0, datetime.now(_kst).year - inp.completion_year)
        else:
            effective_aging = inp.aging_years or 0
        ag_factor = bma_aging_factor(effective_aging)
        uf_factor = BMA_USAGE_FACTORS[inp.building_usage]
        # 제38조 추가 보정
        skip_str_factor = 0.8 if inp.bma_skip_structural else 1.0
        skip_util_factor = 0.9 if inp.bma_skip_utility else 1.0
        adj_combined = ag_factor * uf_factor * skip_str_factor * skip_util_factor

        # 산식 단계별 표시
        manhours_formula.append(ManhourFormulaStep(
            label="별표 1 — 점검책임자",
            value=base_responsible,
            note=f"{int(inp.gross_floor_area):,}㎡ {inp.bma_inspection_type}"
            + (" (구조 +1)" if structural_extra else ""),
        ))
        manhours_formula.append(ManhourFormulaStep(
            label="별표 1 — 점검자",
            value=base_inspector,
            note=f"{int(inp.gross_floor_area):,}㎡ {inp.bma_inspection_type}",
        ))
        if ftype != "기본" and inp.sub_facility_areas:
            manhours_formula.append(ManhourFormulaStep(
                label="제37조 군집건축물",
                value=responsible + inspector,
                note=f"{ftype} · 부속 {len(inp.sub_facility_areas)}동",
            ))
        manhours_formula.append(ManhourFormulaStep(
            label="경과년수 보정 (별표 3-1)",
            operator="×", value=ag_factor,
            note=(
                f"준공 {inp.completion_year}년 → {effective_aging}년 경과"
                if inp.completion_year else f"{effective_aging}년"
            ),
        ))
        manhours_formula.append(ManhourFormulaStep(
            label="용도 보정 (별표 3-2)",
            operator="×", value=uf_factor, note=inp.building_usage,
        ))
        if inp.bma_skip_structural:
            manhours_formula.append(ManhourFormulaStep(
                label="제38조② 구조안전 생략",
                operator="×", value=0.8, note="구조안전 점검 생략",
            ))
        if inp.bma_skip_utility:
            manhours_formula.append(ManhourFormulaStep(
                label="제38조③ 급수 등 생략",
                operator="×", value=0.9, note="급수·배수·냉난방·환기 생략",
            ))
        manhours_formula.append(ManhourFormulaStep(
            label="조정비계 (소계 × 적용)",
            value=adj_combined,
            note=f"× {adj_combined:.4g}",
        ))

        # ── Step 4: 직접인건비 ──────────────────────────────
        direct_labor = int(responsible * responsible_rate) + int(
            inspector * inspector_rate
        )

        # ── Step 5: 제경비/기술료/직접경비 (제34/35/36조) ──
        overhead = int(direct_labor * (inp.overhead_pct / 100))
        tech_fee = int((direct_labor + overhead) * (inp.tech_fee_pct / 100))
        direct_expense = float(DIRECT_EXPENSE_FIXED)

        direct_expense_breakdown.append(OptionalTaskBreakdown(
            label="직접경비 일괄 (제36조)",
            amount=direct_expense,
            note="여비·차량·현장경비·위험수당 등 100,000원 일괄",
        ))

        subtotal_before_adj = direct_labor + overhead + tech_fee + direct_expense

        # ── Step 6: 보정비계 적용 (소계 × 조정) ─────────────
        adjusted = subtotal_before_adj * adj_combined

        # ── Step 7: 선택과업비 (제39조 마감재 해체·복구) ───
        if inp.bma_optional_task_amount > 0:
            adjusted += inp.bma_optional_task_amount
            optional_tasks.append(OptionalTaskBreakdown(
                label="선택과업 (제39조 — 마감재 해체·복구)",
                amount=inp.bma_optional_task_amount,
                note="사용자 직접 입력 — 적산자료 참조",
            ))

        # subtotal은 표시용 (조정 전 + 선택과업 미포함). adjusted_pct는 무시
        # (BMA는 산정표가 자체 보정비계 적용 — adjustment_pct 파라미터 사용 X).
        subtotal = subtotal_before_adj
        mh = responsible + inspector
        mh_outdoor = 0.0  # BMA는 외업/내업 분리 X (산정표에 명시 X)
    else:
        # 수동 fallback — 기존 PR-Q4 흐름
        responsible = inp.inspection_responsible_days or 0
        inspector = inp.inspection_inspector_days or 0
        direct_labor = int(responsible * responsible_rate) + int(
            inspector * inspector_rate
        )
        if inp.direct_expense_items:
            direct_expense = sum(item.amount for item in inp.direct_expense_items)
        else:
            direct_expense = (
                inp.printing_fee + inp.survey_fee + 25_000 * inp.transport_persons
            )
        overhead = int(direct_labor * (inp.overhead_pct / 100))
        tech_fee = int((direct_labor + overhead) * (inp.tech_fee_pct / 100))
        subtotal = direct_labor + overhead + tech_fee + direct_expense
        adjusted = subtotal * (inp.adjustment_pct / 100)
        mh = responsible + inspector
        mh_outdoor = 0.0

    adjusted_int = int(_excel_round_half_up(adjusted, 0))
    if inp.final_override is not None:
        final_amount = int(inp.final_override)
        truncated = adjusted_int - final_amount
    else:
        unit = inp.truncate_unit if inp.truncate_unit > 0 else 1
        truncated = adjusted_int % unit
        final_amount = adjusted_int - truncated

    vat_amount = int(_excel_round_half_up(final_amount * 0.1, 0))
    final_with_vat = final_amount + vat_amount

    per_pyeong_area = inp.gross_floor_area / 3.3 if inp.gross_floor_area else 0
    per_pyeong = final_amount / per_pyeong_area if per_pyeong_area else 0

    return QuoteResult(
        manhours_baseline=0,
        manhours_baseline_rounded=0,
        manhours_total=int(round(mh)),
        direct_labor=direct_labor,
        direct_expense=direct_expense,
        overhead=overhead,
        tech_fee=tech_fee,
        subtotal=subtotal,
        adjusted=adjusted,
        truncated=truncated,
        final=final_amount,
        vat_amount=vat_amount,
        final_with_vat=final_with_vat,
        per_pyeong_area=per_pyeong_area,
        per_pyeong=per_pyeong,
        optional_tasks=optional_tasks,
        direct_expense_breakdown=direct_expense_breakdown,
        manhours_formula=manhours_formula,
        manhours_outdoor=mh_outdoor,
        manhours_indoor=mh - mh_outdoor if auto_mode else 0.0,
    )


def _calculate_inspection_legal(inp: QuoteInput) -> QuoteResult:
    """정기안전점검 + 정밀점검 + 정밀안전진단 통합 strategy (PR-Q5/Q6).

    xlsx 시특법상 대가기준 sheet의 산출 흐름 transcribe.
    종류 분기는 시특법 sheet F11 코드(1=정밀안전진단/2=정밀점검/3=정기점검)에
    해당하지만 backend 흐름은 단일 — overhead/tech/adj/truncate default 차이만
    frontend QUOTE_TYPE_DEFAULTS에서 적용.

    산출
    - 인.일 = manhours_override (사용자가 시특법 sheet 4계수 곱한 H40 결과 입력)
    - direct_labor = ROUNDDOWN(인.일 × 310,884, 0)            # C59
    - overhead     = INT(direct_labor × 1.1)                  # D59 = INT(C59 × D54)
    - tech_fee     = INT((direct_labor + overhead) × 0.2)     # E59 = INT((C59+D59) × E54)
    - direct_expense = Σ direct_expense_items                  # F59 = J51 (사용자 입력 합계)
    - subtotal     = direct_labor + overhead + tech_fee + direct_expense   # J53
    - adjusted     = subtotal × adjustment_pct/100             # J56/J57
    - 절삭: 정기 100_000 / 정밀 1_000_000 (frontend default 분기, 사용자 변경 가능)

    xlsx 검증
    - 정기 (시특법 F11=3, mh=15.24, adj=0.27, unit=100_000, 직접경비=1,237,272):
        direct_labor = floor(15.24 × 310884) = 4,737,872   # C59
        overhead     = int(4737872 × 1.1)    = 5,211,659   # D59
        tech_fee     = int(9949531 × 0.2)    = 1,989,906   # E59
        subtotal     = 13,176,709                          # J53 (xlsx 13,176,708.75)
        adjusted     = 13,176,709 × 0.27     = 3,557,711.43
        truncated    = 57,711, final         = 3,500,000   # J58 ≈ xlsx 3,500,000.36
    - 정밀 (시특법 F11=2, mh=36.19, adj=0.88, unit=1_000_000, 직접경비=5,796,625):
        direct_labor = floor(36.19 × 310884) = 11,250,891  # C59
        overhead     = int(11250891 × 1.1)   = 12,375,980  # D59
        tech_fee     = int(23626871 × 0.2)   = 4,725,374   # E59
        subtotal     = 34,148,870                          # J54
        adjusted     = 34,148,870 × 0.88     = 30,051,005.6
        truncated    = 51,006, final         = 30,000,000  # J59 ≈ xlsx 29,999,999.6
    - 정밀안전진단 (시특법 F11=1, mh=54.42, overhead=1.2, tech=0.4, adj=0.45,
      unit=1_000_000, 직접경비=4,498,265):
        direct_labor = floor(54.42 × 310884) = 16,918,307  # C59
        overhead     = int(16918307 × 1.2)   = 20,301,968  # D59
        tech_fee     = int(37220275 × 0.4)   = 14,888,110  # E59
        subtotal     = 56,606,650                          # J54
        adjusted     = 56,606,650 × 0.45     = 25,472,992.5
        truncated    = 472,993, final        = 25,000,000  # J59 ≈ xlsx 24,999,999.5
    PR-Q5b 자동 산정 분기
    --------------------
    inp.structure_form이 STRUCTURE_FACTORS 키이고 inp.gross_floor_area>0이면
    별표 22 보간 + 별표 23 조정 + 제62조 보정으로 인.일·외업·직접경비 자동 산정.
    그 외엔 기존 manhours_override 흐름 (backward 호환).
    """
    import math

    from app.services.inspection_legal_table import (
        STRUCTURE_FACTORS,
        USAGE_FACTORS,
        aging_factor,
        apply_facility_form,
        complexity_factor,
        interpolate_base,
        prev_report_factor,
    )

    # 시특법 종류 매핑 — QuoteType → InspectionType.
    # 건축물관리법점검(INSPECTION_BMA)은 별도 strategy(_calculate_inspection_bma) 사용.
    qtype_to_itype = {
        QuoteType.INSPECTION_REGULAR: "정기점검",
        QuoteType.INSPECTION_DETAIL: "정밀점검",
        QuoteType.INSPECTION_DIAGNOSIS: "정밀안전진단",
    }
    itype = qtype_to_itype.get(inp.quote_type)

    auto_mode = (
        itype is not None
        and inp.gross_floor_area > 0
        and inp.structure_form in STRUCTURE_FACTORS
        and inp.building_usage in USAGE_FACTORS
    )

    rate = _resolve_rate(inp.engineer_grade, "고급기술자")
    direct_expense_breakdown: list[OptionalTaskBreakdown] = []
    manhours_formula: list[ManhourFormulaStep] = []

    if auto_mode:
        # ── Step 1: 별표 22 base 인.일 (전체/외업) ─────────
        base = interpolate_base(inp.gross_floor_area, itype)
        if base is None:
            # 5,000㎡ 미만 정밀점검·진단 — 자동 산정 불가, manhours_override fallback
            auto_mode = False
        else:
            base_total, base_outdoor = base

            # ── Step 2: 시설물 형태 (제61조) ─────────────────
            def _base_lookup_total(area: float) -> float:
                r = interpolate_base(area, itype)
                return r[0] if r else 0.0

            def _base_lookup_outdoor(area: float) -> float:
                r = interpolate_base(area, itype)
                return r[1] if r else 0.0

            ftype = inp.facility_type or "기본"
            if ftype != "기본" and inp.sub_facility_areas:
                base_total_adj = apply_facility_form(
                    base_total, ftype, inp.sub_facility_areas, _base_lookup_total
                )
                base_outdoor_adj = apply_facility_form(
                    base_outdoor, ftype, inp.sub_facility_areas, _base_lookup_outdoor
                )
            else:
                base_total_adj = base_total
                base_outdoor_adj = base_outdoor

            # ── Step 3: 별표 23 + 제62조 보정 곱 ──────────────
            sf_factor = STRUCTURE_FACTORS[inp.structure_form]
            uf_factor = USAGE_FACTORS[inp.building_usage]
            # 경과년수 — completion_year 우선 (산정 시점 KST 기준), 없으면 aging_years
            if inp.completion_year:
                from datetime import datetime, timedelta, timezone
                _kst = timezone(timedelta(hours=9))
                effective_aging = max(0, datetime.now(_kst).year - inp.completion_year)
            else:
                effective_aging = inp.aging_years or 0
            ag_factor = aging_factor(effective_aging)
            cx_factor = complexity_factor(inp.complexity or "보통")
            pr_factor = prev_report_factor(inp.prev_report or "미제공")
            correction = sf_factor * uf_factor * ag_factor * cx_factor * pr_factor
            mh_base = base_total_adj * correction
            mh_outdoor = base_outdoor_adj * correction

            # 산식 단계별 — PDF 2페이지 "기본과업 인.일 산식" 표시용
            manhours_formula.append(ManhourFormulaStep(
                label="별표 22 기준인원수",
                value=base_total_adj,
                note=f"{int(inp.gross_floor_area):,}㎡ {itype}"
                + (f" · 시설물 형태: {inp.facility_type}" if inp.facility_type and inp.facility_type != "기본" else ""),
            ))
            manhours_formula.append(ManhourFormulaStep(
                label="구조형식 보정 (별표 23-1)",
                operator="×", value=sf_factor, note=inp.structure_form,
            ))
            manhours_formula.append(ManhourFormulaStep(
                label="용도 보정 (별표 23-2)",
                operator="×", value=uf_factor, note=inp.building_usage,
            ))
            manhours_formula.append(ManhourFormulaStep(
                label="경과년수 보정 (제62조-2)",
                operator="×", value=ag_factor,
                note=(
                    f"준공 {inp.completion_year}년 → {effective_aging}년 경과"
                    if inp.completion_year else f"{effective_aging}년"
                ),
            ))
            manhours_formula.append(ManhourFormulaStep(
                label="구조복잡도 보정 (제62조-1)",
                operator="×", value=cx_factor, note=inp.complexity or "보통",
            ))
            manhours_formula.append(ManhourFormulaStep(
                label="전차보고서 보정 (제62조-3)",
                operator="×", value=pr_factor, note=inp.prev_report or "미제공",
            ))
            manhours_formula.append(ManhourFormulaStep(
                label="기본과업 인.일 소계", value=mh_base, note="별표 22 + 보정 누적",
            ))

            # ── Step 3.5: 추가과업 인.일 합산 (별표 26-10-(3)·-15) ──
            # 구조해석·내진평가는 별표 22 보정 인.일에 합산되어 직접인건비 산정 base.
            # 실측도면·자유입력은 별도 합산 (Step 7 이후).
            from app.services.inspection_legal_table import (
                interpolate_analysis_persons,
            )

            additional_analysis_persons = 0.0  # 구조해석 인 (개소당 × 개소)
            additional_seismic_persons = 0.0   # 내진평가 인
            if inp.opt_structural_analysis and inp.gross_floor_area > 0:
                additional_analysis_persons = (
                    interpolate_analysis_persons(
                        inp.gross_floor_area, inp.opt_analysis_struct_type
                    )
                    * inp.opt_analysis_count
                )
            if inp.opt_seismic_eval and inp.gross_floor_area > 0:
                base_persons = (
                    interpolate_analysis_persons(
                        inp.gross_floor_area, inp.opt_analysis_struct_type
                    )
                    * inp.opt_analysis_count
                )
                additional_seismic_persons = (
                    base_persons * inp.opt_seismic_multiplier
                )

            # 추가과업 인은 모두 내업으로 간주 (시설물 외부 현장조사 X).
            mh_total = mh_base + additional_analysis_persons + additional_seismic_persons

            # 산식 단계별 — 추가과업 합산 row
            if additional_analysis_persons > 0:
                manhours_formula.append(ManhourFormulaStep(
                    label="구조해석 (별표 26-10-(3))",
                    operator="+",
                    value=additional_analysis_persons,
                    note=f"{inp.opt_analysis_struct_type} {inp.opt_analysis_count}개소",
                ))
            if additional_seismic_persons > 0:
                method_label = "간략" if inp.opt_seismic_multiplier <= 2.0 else "정밀"
                manhours_formula.append(ManhourFormulaStep(
                    label="내진성 평가 (별표 26-15)",
                    operator="+",
                    value=additional_seismic_persons,
                    note=f"{method_label} ×{inp.opt_seismic_multiplier:g}",
                ))
            if additional_analysis_persons > 0 or additional_seismic_persons > 0:
                manhours_formula.append(ManhourFormulaStep(
                    label="전체 인.일 (직접인건비 산정 base)",
                    value=mh_total,
                    note="기본과업 + 추가과업 합산",
                ))

            # ── Step 4: 직접인건비 (합산 인.일 기반) ──────────
            direct_labor = int(math.floor(mh_total * rate))

            # ── Step 5: 직접경비 (별표 25) ────────────────
            persons_by_type = {"정기점검": 2, "정밀점검": 8, "정밀안전진단": 10}
            persons = persons_by_type[itype]
            travel = persons * inp.travel_unit_cost

            # 차량 일수 = ceil(외업 인.일 / 4) — 외업 4인 1대 기준
            vehicle_days = math.ceil(mh_outdoor / 4) if mh_outdoor > 0 else 0
            # 일별 비용 = 차량 손료 + 주연료(10ℓ) + 잡품(주연료 × 10%)
            fuel_with_misc = inp.fuel_unit_price * 10 * 1.1
            vehicle = vehicle_days * (inp.vehicle_daily_cost + fuel_with_misc)

            # 보조인부·위험수당·기계기구는 사용자 입력값 그대로 사용 (default 0).
            # 사용자가 단가/% 명시 입력해야 산정에 반영. 별표 25 권장 비율은
            # frontend 안내문 + 별표 25 비고 참조 (정기 0% / 정밀점검 5% / 진단 10%).
            helper = mh_outdoor * 0.40 * inp.helper_daily_wage
            risk = direct_labor * (inp.risk_pct / 100)
            machine = direct_labor * (inp.machine_pct / 100)

            print_cost = inp.print_unit_cost * inp.print_copies

            direct_expense = int(
                round(travel + vehicle + helper + risk + machine + print_cost)
            )
            mh = mh_total

            # 별표 25 직접경비 항목별 분해 — PDF 2페이지 표시용
            direct_expense_breakdown = [
                OptionalTaskBreakdown(
                    label="여비·현장체재비",
                    amount=travel,
                    note=f"{persons}인 × {int(inp.travel_unit_cost):,}원 (1회 왕복)",
                ),
                OptionalTaskBreakdown(
                    label="차량운행비",
                    amount=vehicle,
                    note=f"{vehicle_days}일 × ({int(inp.vehicle_daily_cost):,}원 손료 + {int(fuel_with_misc):,}원 연료·잡품)",
                ),
                OptionalTaskBreakdown(
                    label="현지보조인부 노임",
                    amount=helper,
                    note=f"외업 {mh_outdoor:.2f}인.일 × 40% × {int(inp.helper_daily_wage):,}원",
                ),
                OptionalTaskBreakdown(
                    label="위험수당",
                    amount=risk,
                    note=f"직접인건비 {direct_labor:,}원 × {inp.risk_pct:g}%",
                ),
                OptionalTaskBreakdown(
                    label="기계·기구 손료",
                    amount=machine,
                    note=f"직접인건비 {direct_labor:,}원 × {inp.machine_pct:g}%",
                ),
                OptionalTaskBreakdown(
                    label="보고서 인쇄비",
                    amount=print_cost,
                    note=f"{int(inp.print_unit_cost):,}원/책 × {inp.print_copies}부",
                ),
            ]

    if not auto_mode:
        # ── 기존 manhours_override 흐름 (backward 호환) ──
        mh = float(inp.manhours_override) if inp.manhours_override is not None else 0.0
        direct_labor = int(math.floor(mh * rate))
        # 시특법 종류는 legacy direct_expense_items / printing_fee 등을 무시.
        # 별표 25/26 자동 산정만 사용 (auto_mode 미달 케이스도 직접경비 0 → 사용자가
        # 시특법 입력값을 보강해 자동 산정 활성화하도록 유도).
        if itype is not None:
            direct_expense = 0.0
        elif inp.direct_expense_items:
            direct_expense = sum(item.amount for item in inp.direct_expense_items)
        else:
            direct_expense = (
                inp.printing_fee + inp.survey_fee + 25_000 * inp.transport_persons
            )

    overhead = int(direct_labor * (inp.overhead_pct / 100))
    tech_fee = int((direct_labor + overhead) * (inp.tech_fee_pct / 100))

    # ── 별표 26 추가과업 합산 (자동 산정 모드에서만) ───────
    # 산식 분기:
    #  · 인.일 합산 (구조해석·내진평가): 이미 Step 3.5에서 mh_total에 합산되어
    #    direct_labor·overhead·tech_fee 모두 영향. 여기선 표시용 breakdown만 기록.
    #  · 별도 합산 (실측도면·자유입력): direct_expense에 합산 → subtotal/adjusted 영향.
    # 실측도면 base = subtotal_base(별표 25 기본과업 + 인.일 합산 후).
    optional_tasks: list[OptionalTaskBreakdown] = []
    if auto_mode:
        from app.services.inspection_legal_table import drawing_pct

        subtotal_base = direct_labor + overhead + tech_fee + direct_expense

        # B. 구조해석 — 인.일 합산 (직접인건비 산정 포함). 표시용 amount = 인 × rate
        if additional_analysis_persons > 0:
            amount = additional_analysis_persons * rate
            optional_tasks.append(OptionalTaskBreakdown(
                label=f"구조해석 ({inp.opt_analysis_struct_type}, {inp.opt_analysis_count}개소)",
                persons=additional_analysis_persons,
                unit_rate=rate,
                amount=amount,
                note=f"{additional_analysis_persons:g}인 → 기본과업 인.일 합산 (직접인건비 포함)",
            ))

        # C. 내진성 평가 — 인.일 합산 (직접인건비 산정 포함)
        if additional_seismic_persons > 0:
            amount = additional_seismic_persons * rate
            method_label = "간략" if inp.opt_seismic_multiplier <= 2.0 else "정밀"
            optional_tasks.append(OptionalTaskBreakdown(
                label=f"내진성 평가 ({method_label} ×{inp.opt_seismic_multiplier:g})",
                persons=additional_seismic_persons,
                unit_rate=rate,
                amount=amount,
                note=f"{additional_seismic_persons:g}인 → 기본과업 인.일 합산 (직접인건비 포함)",
            ))

        # A. 실측도면 — 별도 합산 (subtotal_base × pct → direct_expense)
        opt_extra_total = 0.0
        if inp.opt_field_drawings:
            pct = drawing_pct(inp.opt_field_drawings_scope)
            amount = subtotal_base * pct
            opt_extra_total += amount
            optional_tasks.append(OptionalTaskBreakdown(
                label=f"실측도면 ({inp.opt_field_drawings_scope} {int(pct*100)}%)",
                base_pct=pct,
                base_amount=subtotal_base,
                amount=amount,
                note=f"기본과업비 {int(subtotal_base):,}원 × {int(pct*100)}% → 직접경비 추가",
            ))

        # 그 외 자유 입력 — 별도 합산 (direct_expense)
        for item in inp.opt_other_items:
            opt_extra_total += item.amount
            optional_tasks.append(OptionalTaskBreakdown(
                label=item.name or "기타 추가과업",
                amount=item.amount,
                note="사용자 직접 입력 → 직접경비 추가",
            ))

        direct_expense += opt_extra_total

    subtotal = direct_labor + overhead + tech_fee + direct_expense
    adjusted = subtotal * (inp.adjustment_pct / 100)

    adjusted_int = int(_excel_round_half_up(adjusted, 0))
    if inp.final_override is not None:
        final_amount = int(inp.final_override)
        truncated = adjusted_int - final_amount
    else:
        unit = inp.truncate_unit if inp.truncate_unit > 0 else 1
        truncated = adjusted_int % unit
        final_amount = adjusted_int - truncated

    vat_amount = int(_excel_round_half_up(final_amount * 0.1, 0))
    final_with_vat = final_amount + vat_amount

    per_pyeong_area = inp.gross_floor_area / 3.3 if inp.gross_floor_area else 0
    per_pyeong = final_amount / per_pyeong_area if per_pyeong_area else 0

    return QuoteResult(
        manhours_baseline=0,
        manhours_baseline_rounded=0,
        manhours_total=int(round(mh)),
        direct_labor=direct_labor,
        direct_expense=direct_expense,
        overhead=overhead,
        tech_fee=tech_fee,
        subtotal=subtotal,
        adjusted=adjusted,
        truncated=truncated,
        final=final_amount,
        vat_amount=vat_amount,
        final_with_vat=final_with_vat,
        per_pyeong_area=per_pyeong_area,
        per_pyeong=per_pyeong,
        optional_tasks=optional_tasks,
        direct_expense_breakdown=direct_expense_breakdown if auto_mode else [],
        manhours_formula=manhours_formula,
        manhours_outdoor=mh_outdoor if auto_mode else 0.0,
        manhours_indoor=(mh_total - mh_outdoor) if auto_mode else 0.0,
    )
