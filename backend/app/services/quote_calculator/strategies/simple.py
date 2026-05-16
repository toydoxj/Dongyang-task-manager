"""소형 단순 strategy 4개 묶음.

PR-DH (Phase 4-J 18단계): quote_calculator/__init__.py에서 분리.

| strategy | 단가 default | 특이점 |
|---|---|---|
| field_support (현장기술지원, PR-Q2) | 고급기술자 | 자동 인.일 산출 X (manhours_override 필수). adjusted = subtotal*adj% + direct_expense |
| supervision (구조감리, PR-Q3) | 기술사 | tech_fee 30%(default). subtotal에 직접경비 포함, adjusted는 단순 ×adj% |
| reinforcement_design (내진보강설계) | 고급기술자 | subtotal에 직접경비 포함, adjusted는 단순 ×adj% |
| third_party_review (3자검토) | 특급기술자 | reinforcement_design과 동일 흐름, 단가만 다름 |

4개 모두 ~60-75줄, 단일 인.일 입력 모델, helper 의존 동일하므로 응집도
유지하며 한 모듈에 묶는다 (PR-DE struct가 한 짝, PR-DF inspection이 한 짝
패턴의 연장).

helper(_excel_round_half_up / _resolve_rate) + model(QuoteInput / QuoteResult)
은 __init__.py에 그대로 두고 import. _DISPATCH 정의 직전에 본 모듈을 import
하므로 partial loading 시점에 attribute 모두 확보됨 (PR-DE/DF/DG 검증 패턴).
"""
from __future__ import annotations

from app.services.quote_calculator import (
    QuoteInput,
    QuoteResult,
    _excel_round_half_up,
    _resolve_rate,
)


def _calculate_field_support(inp: QuoteInput) -> QuoteResult:
    """현장기술지원용역견적서 산출 (PR-Q2).

    구조설계와 거의 동일 흐름이나 핵심 차이:
    - baseline_manhours 자동 산출 X — 사용자가 인.일을 직접 입력
      (manhours_override 필수, 없으면 0)
    - 단가가 다름: 고급기술자 253,985원/인.일
    - 산출 행 라벨이 동일하므로 PDF template 그대로 재사용 가능
    - 직접경비/제경비(110%)/기술료(20%)/조정/절삭 모두 구조설계와 동일
    - default 조정%는 80 (xlsx 실 사례)

    xlsx 검증 (현장지원26-07-002.xlsx):
    K17=5인.일, H27=80%, 직접경비=50,000(교통비 25,000×2)
    → K27=2,610,168.8 → K28=610,169 (백만 미만) → K29=2,000,000
    """
    # 인.일 — 직접 입력 우선, 없으면 0 (현장지원은 자동 산출 모델 없음)
    mh_total = (
        int(inp.manhours_override) if inp.manhours_override is not None else 0
    )

    # 직접인건비 — 단가만 다름 (253,985원/인.일)
    # 단가 — 사용자 선택 등급 우선, 없으면 default(고급기술자).
    direct_labor = mh_total * _resolve_rate(inp.engineer_grade, "고급기술자")

    # 직접경비: 동적 list 우선, 없으면 legacy 합산
    if inp.direct_expense_items:
        direct_expense = sum(item.amount for item in inp.direct_expense_items)
    else:
        direct_expense = (
            inp.printing_fee + inp.survey_fee + 25_000 * inp.transport_persons
        )

    overhead = direct_labor * (inp.overhead_pct / 100)
    tech_fee = (direct_labor + overhead) * (inp.tech_fee_pct / 100)
    subtotal = direct_labor + overhead + tech_fee
    adjusted = subtotal * (inp.adjustment_pct / 100) + direct_expense

    # 절삭 — final_override 우선, 없으면 truncate_unit으로 절삭
    adjusted_int = int(_excel_round_half_up(adjusted, 0))
    if inp.final_override is not None:
        final_amount = int(inp.final_override)
        truncated = adjusted_int - final_amount
    else:
        unit = inp.truncate_unit if inp.truncate_unit > 0 else 1
        truncated = adjusted_int % unit
        final_amount = adjusted_int - truncated

    # VAT
    vat_amount = int(_excel_round_half_up(final_amount * 0.1, 0))
    final_with_vat = final_amount + vat_amount

    # 평당 — 현장지원은 회당 견적이라 의미 약함. 호환을 위해 채워둠.
    per_pyeong_area = inp.gross_floor_area / 3.3 if inp.gross_floor_area else 0
    per_pyeong = final_amount / per_pyeong_area if per_pyeong_area else 0

    return QuoteResult(
        manhours_baseline=0,
        manhours_baseline_rounded=0,
        manhours_total=mh_total,
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
    )


def _calculate_supervision(inp: QuoteInput) -> QuoteResult:
    """구조감리용역견적서 산출 (PR-Q3).

    구조설계와 산출 모델 자체가 다름:
    - 인.일 = 현장 방문회수 × 3 (회당 3인.일 hardcoded — xlsx K16=H14*3).
      사용자가 manhours_override로 81 직접 입력하는 패턴 (또는 visit_count
      신규 필드는 추후). 현 PR은 manhours_override 활용.
    - 단가: 기술사 446,055원/인.일 (xlsx E18 표기는 452,718이나 K18 수식은
      446055로 hardcoded — xlsx 사본 정정 안 된 oldest로 보임. 446055 사용)
    - tech_fee 30% (구조설계 20%)
    - **K25 합계가 직접경비 포함** (구조설계는 ⑧=①+⑥+⑦, 감리는
      ⑤+①+⑥+⑦ 모두 더함). 따라서 K26 조정은 단순 ×adj% (직접경비 더함 X)

    xlsx 검증 (구조감리26-08-003.xlsx K28=54,000,000):
    K16=81 (=H14*3, H14=27회), K22=800,000 (=200,000*4 외업), H26=55%
    → K18=36,130,455 → K23=39,743,500.5 → K24=22,762,186.65
    → K25=99,436,142.15 → K26=54,689,878.1825 → K28=54,000,000
    """
    mh_total = (
        int(inp.manhours_override) if inp.manhours_override is not None else 0
    )

    # 구조감리 default = 기술사. 사용자 선택 등급 우선.
    direct_labor = mh_total * _resolve_rate(inp.engineer_grade, "기술사")

    if inp.direct_expense_items:
        direct_expense = sum(item.amount for item in inp.direct_expense_items)
    else:
        direct_expense = (
            inp.printing_fee + inp.survey_fee + 25_000 * inp.transport_persons
        )

    overhead = direct_labor * (inp.overhead_pct / 100)
    tech_fee = (direct_labor + overhead) * (inp.tech_fee_pct / 100)
    # 구조감리: subtotal에 직접경비 포함, adjusted는 직접경비 더하지 않음
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
        manhours_total=mh_total,
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
    )


def _calculate_reinforcement_design(inp: QuoteInput) -> QuoteResult:
    """내진보강설계 strategy.

    사용자가 4 모듈(내진성능평가/내진보강설계/3자검토/구조감리) 중 일부를
    별 영업으로 분리 작성하는 패턴. parent_lead_id로 묶어 통합 PDF 출력 (PR-G1).

    산출은 단순 — 단일 인.일 × 단가 → overhead × 110% → tech × 20% → 합산
    → 조정 → 절삭. xlsx L81~L84 검증:
        mh=9, rate=242,055
        direct = 9 × 242,055 = 2,178,495   # L81
        oh     = 2,178,495 × 1.1 = 2,396,344.5  # L82
        tech   = (2,178,495+2,396,344.5) × 0.2 = 914,967.9  # L83
        subtotal = 5,489,807.4              # L84
    """
    mh_total = (
        int(inp.manhours_override) if inp.manhours_override is not None else 0
    )
    # default = 고급기술자. 사용자 선택 등급 우선.
    direct_labor = mh_total * _resolve_rate(inp.engineer_grade, "고급기술자")

    if inp.direct_expense_items:
        direct_expense = sum(item.amount for item in inp.direct_expense_items)
    else:
        direct_expense = (
            inp.printing_fee + inp.survey_fee + 25_000 * inp.transport_persons
        )

    overhead = direct_labor * (inp.overhead_pct / 100)
    tech_fee = (direct_labor + overhead) * (inp.tech_fee_pct / 100)
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
        manhours_total=mh_total,
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
    )


def _calculate_third_party_review(inp: QuoteInput) -> QuoteResult:
    """내진보강설계 검증(3자검토) strategy.

    내진보강설계와 동일 흐름이나 단가는 특급기술자(건설) 373,353원/일 (사용자 명시).
    xlsx 옛 사례(L85~L88, 단가 292,249)와 결과 다를 수 있음.
    """
    mh_total = (
        int(inp.manhours_override) if inp.manhours_override is not None else 0
    )
    # 3자검토 default = 특급기술자. 사용자 선택 등급 우선.
    direct_labor = mh_total * _resolve_rate(inp.engineer_grade, "특급기술자")

    if inp.direct_expense_items:
        direct_expense = sum(item.amount for item in inp.direct_expense_items)
    else:
        direct_expense = (
            inp.printing_fee + inp.survey_fee + 25_000 * inp.transport_persons
        )

    overhead = direct_labor * (inp.overhead_pct / 100)
    tech_fee = (direct_labor + overhead) * (inp.tech_fee_pct / 100)
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
        manhours_total=mh_total,
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
    )
