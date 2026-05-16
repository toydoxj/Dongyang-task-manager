"""내진성능평가 strategy (PR-Q8) + 면적·도면 보간 helper.

PR-DG (Phase 4-J 17단계): quote_calculator/__init__.py에서 분리.

`_calculate_seismic_eval`만 _DISPATCH가 호출하지만, 그 안에서 사용하는
`interpolate_seismic_manhours` + `_SEISMIC_AREA_TABLE`이 다른 strategy에선
사용되지 않으므로 함께 이동 (모듈 응집도). 외부에서 import하는 곳도 없음.

helper(_excel_round_half_up / _resolve_rate) + model(QuoteInput / QuoteResult)은
__init__.py에 그대로 두고 import. PR-DE/DF struct·inspection과 동일 패턴.
"""
from __future__ import annotations

from app.services.quote_calculator import (
    QuoteInput,
    QuoteResult,
    _excel_round_half_up,
    _resolve_rate,
)


# 내진성능평가 면적·도면 유무 보간 table (PR-Q8b).
# xlsx V48:AC56 영역 그대로 — 사장 운영 양식의 표준 인.일 기준.
# 컬럼: (연면적, 도면有_외업, 도면有_내업, 도면無_외업, 도면無_내업, 해석base)
_SEISMIC_AREA_TABLE: list[tuple[int, int, int, int, int, int]] = [
    (200,    4,  2,   8,  4,   7),
    (500,    5,  3,  10,  6,   9),
    (1000,   7,  4,  14,  8,  11),
    (3000,   9,  5,  18, 10,  15),
    (5000,  11,  6,  22, 12,  18),
    (10000, 12,  6,  24, 12,  20),
    (30000, 21,  8,  42, 16,  28),
    (50000, 29, 10,  58, 20,  35),
    (100000,50, 15, 100, 30,  53),
]


def interpolate_seismic_manhours(
    area_m2: float, *, has_drawings: bool
) -> tuple[float, float, float]:
    """xlsx V47~AC59 면적·도면 유무 보간 → (외업, 내업, 해석base) 인.일 (PR-Q8b).

    선형 보간 — area가 table 두 행 사이에 있으면 비례 계산. table 범위 밖
    (200 미만, 100,000 초과)은 끝 값으로 cap (사용자가 수동 override 권장).

    해석 base는 4계수(방법별·경년·구조형식·용도) 곱하기 전 값. 실제 사장이
    적용하는 해석 인.일은 base × 계수곱이라 사용자가 xlsx 보고 직접 곱해 입력
    하는 모델 (4계수가 매 견적마다 다름).

    검증: area=6602.3, has_drawings=False (xlsx F44='무')
        ratio = (6602.3 - 5000) / 5000 = 0.32046
        외업 = 22 + (24 - 22) × 0.32046 = 22.64092  ← xlsx AA58
        내업 = 12 + (12 - 12) × 0.32046 = 12        ← xlsx AB58
        해석 = 18 + (20 - 18) × 0.32046 = 18.64092  ← xlsx AC58
    """
    table = _SEISMIC_AREA_TABLE
    # 범위 밖 cap
    if area_m2 <= table[0][0]:
        row = table[0]
        outdoor = row[1] if has_drawings else row[3]
        indoor = row[2] if has_drawings else row[4]
        return (float(outdoor), float(indoor), float(row[5]))
    if area_m2 >= table[-1][0]:
        row = table[-1]
        outdoor = row[1] if has_drawings else row[3]
        indoor = row[2] if has_drawings else row[4]
        return (float(outdoor), float(indoor), float(row[5]))

    # 선형 보간
    for i in range(len(table) - 1):
        lo, hi = table[i], table[i + 1]
        if lo[0] <= area_m2 <= hi[0]:
            ratio = (area_m2 - lo[0]) / (hi[0] - lo[0])
            yes_out = lo[1] + (hi[1] - lo[1]) * ratio
            yes_in = lo[2] + (hi[2] - lo[2]) * ratio
            no_out = lo[3] + (hi[3] - lo[3]) * ratio
            no_in = lo[4] + (hi[4] - lo[4]) * ratio
            analysis_base = lo[5] + (hi[5] - lo[5]) * ratio
            outdoor = yes_out if has_drawings else no_out
            indoor = yes_in if has_drawings else no_in
            return (outdoor, indoor, analysis_base)

    # 도달 불가 (위 if/loop가 모든 케이스 커버) — 안전 fallback
    row = table[-1]
    outdoor = float(row[1] if has_drawings else row[3])
    indoor = float(row[2] if has_drawings else row[4])
    return (outdoor, indoor, float(row[5]))


def _calculate_seismic_eval(inp: QuoteInput) -> QuoteResult:
    """내진성능평가 strategy (PR-Q8).

    xlsx 산출 흐름은 두 섹션 합산:

    ① 현장조사 (외업/내업 인.일 분리)
       direct_labor = (외업 + 내업) × 300,980 (기술자 단가)
       lodging      = 30,000 × 외업                  (현장체제비, L50)
       machinery    = direct_labor × 10%             (기계기구 손료, L51)
       other        = direct_labor × 10%             (기타 현장경비, L52)
       overhead     = direct_labor × overhead_pct/100 (L53, default 110%)
       tech_fee     = (direct_labor + overhead) × tech_fee_pct/100 (L54, 20%)
       subtotal_1   = ① 모든 항목 합                 (L55)

    ② 내진성능평가 (해석 인.일 단일)
       direct_labor_2 = 해석인일 × 300,980           (L56)
       overhead_2     = direct_labor_2 × 110%        (L57)
       tech_fee_2     = (direct_labor_2 + overhead_2) × 20% (L58)
       subtotal_2     = ② 합                         (L59)

    ③ 합산·조정·절삭
       total          = subtotal_1 + subtotal_2 + direct_expense (L60)
       adjusted       = total × adjustment_pct/100   (L61, default 45%)
       truncated      = adjusted % truncate_unit     (L62, default 백만)
       final          = adjusted - truncated         (L63)

    인.일 자동 산출(연면적·구조도면 유무·해석방법·등급 보간 — xlsx V47~AC59)은
    table 너무 복잡해 backend에 옮기지 않음. 사용자가 xlsx 보고 수동 입력
    (field_outdoor_days/field_indoor_days/analysis_days 신규 필드).

    xlsx 검증 (외업 22.64092, 내업 12, 해석 67.667, adj=0.45, 백만 절삭):
    - field_direct  = 34.64092 × 300,980 = 10,426,224.10  # L48
    - lodging       = 30,000 × 22.64092  =    679,227.6   # L50
    - machinery     = 10,426,224.10×0.1  =  1,042,622.41  # L51
    - other         = 10,426,224.10×0.1  =  1,042,622.41  # L52
    - field_oh      = 10,426,224.10×1.1  = 11,468,846.51  # L53
    - field_tech    = 21,895,070.61×0.2  =  4,379,014.12  # L54
    - subtotal_1   = 29,038,557.16                        # L55
    - analysis_d    = 67.667 × 300,980    = 20,366,413.66  # L56
    - analysis_oh   = 22,403,055.03                       # L57
    - analysis_tech = 8,553,893.74                        # L58
    - subtotal_2   = 51,323,362.42                        # L59
    - total         = 80,361,919.58                        # L60
    - adjusted      = 36,162,863.81                        # L61
    - final         = 36,000,000                           # L63 ≈ xlsx 35,999,999.81
    """
    # PR-Q8b — 외업/내업/해석 인.일이 None이고 has_structural_drawings + 면적이
    # 있으면 xlsx V47~AC59 보간 table로 자동 산출. 사용자 수동 입력은 그대로 우선.
    field_outdoor = inp.field_outdoor_days
    field_indoor = inp.field_indoor_days
    analysis = inp.analysis_days
    if (
        inp.has_structural_drawings is not None
        and inp.gross_floor_area
        and (field_outdoor is None or field_indoor is None or analysis is None)
    ):
        auto_out, auto_in, auto_analysis_base = interpolate_seismic_manhours(
            inp.gross_floor_area,
            has_drawings=inp.has_structural_drawings,
        )
        if field_outdoor is None:
            field_outdoor = auto_out
        if field_indoor is None:
            field_indoor = auto_in
        # 해석 base는 4계수(방법별·경년·구조형식·용도) 곱하기 전 값. 사용자가
        # 수동 입력 안 했으면 base 그대로 사용 — 정확하지 않을 수 있어 결과 패널
        # 확인 필수.
        if analysis is None:
            analysis = auto_analysis_base

    field_outdoor = field_outdoor or 0
    field_indoor = field_indoor or 0
    analysis = analysis or 0
    # default = 고급기술자. 사용자 선택 등급 우선.
    rate = _resolve_rate(inp.engineer_grade, "고급기술자")

    # ① 현장조사
    field_direct = (field_outdoor + field_indoor) * rate
    lodging = 30_000 * field_outdoor
    machinery = field_direct * 0.1
    other_expense = field_direct * 0.1
    field_overhead = field_direct * (inp.overhead_pct / 100)
    field_tech = (field_direct + field_overhead) * (inp.tech_fee_pct / 100)
    field_subtotal = (
        field_direct + lodging + machinery + other_expense + field_overhead + field_tech
    )

    # ② 내진성능평가
    analysis_direct = analysis * rate
    analysis_overhead = analysis_direct * (inp.overhead_pct / 100)
    analysis_tech = (analysis_direct + analysis_overhead) * (inp.tech_fee_pct / 100)
    analysis_subtotal = analysis_direct + analysis_overhead + analysis_tech

    # ③ 추가 직접경비 (사용자 입력) → 합산·조정·절삭
    if inp.direct_expense_items:
        direct_expense = sum(item.amount for item in inp.direct_expense_items)
    else:
        direct_expense = (
            inp.printing_fee + inp.survey_fee + 25_000 * inp.transport_persons
        )

    total = field_subtotal + analysis_subtotal + direct_expense
    adjusted = total * (inp.adjustment_pct / 100)

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

    # QuoteResult는 단일 direct_labor/overhead/tech 슬롯 — 두 섹션 합산해 표시
    mh_total = int(round(field_outdoor + field_indoor + analysis))
    per_pyeong_area = inp.gross_floor_area / 3.3 if inp.gross_floor_area else 0
    per_pyeong = final_amount / per_pyeong_area if per_pyeong_area else 0

    return QuoteResult(
        manhours_baseline=0,
        manhours_baseline_rounded=0,
        manhours_total=mh_total,
        direct_labor=field_direct + analysis_direct,
        # 직접경비는 (체제비 + 기계 + 기타 + 사용자 입력)을 합산 — PDF 표는 단일
        # ②행에 표시되므로 모두 묶음. 추후 PDF 분기 필요.
        direct_expense=lodging + machinery + other_expense + direct_expense,
        overhead=field_overhead + analysis_overhead,
        tech_fee=field_tech + analysis_tech,
        subtotal=field_subtotal + analysis_subtotal,
        adjusted=adjusted,
        truncated=truncated,
        final=final_amount,
        vat_amount=vat_amount,
        final_with_vat=final_with_vat,
        per_pyeong_area=per_pyeong_area,
        per_pyeong=per_pyeong,
    )
