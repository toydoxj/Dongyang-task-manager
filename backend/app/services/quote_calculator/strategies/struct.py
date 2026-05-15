"""구조설계 / 구조검토 strategy.

PR-DE (Phase 4-J 15단계): quote_calculator/__init__.py에서 분리.

두 strategy는 한 짝 — struct_review가 manhours_override 처리만 다르고
struct_design을 위임 호출한다.

helper(baseline_manhours / _excel_round_half_up / _resolve_rate) +
model(QuoteInput / QuoteResult)은 __init__.py에 그대로 두고 import.
__init__.py는 _DISPATCH 정의 직전에 본 모듈을 import하므로 partial
loading 시점에 helper/model attribute가 모두 확보된 상태 → 순환 import
충돌 없음.
"""
from __future__ import annotations

from app.services.quote_calculator import (
    QuoteInput,
    QuoteResult,
    _excel_round_half_up,
    _resolve_rate,
    baseline_manhours,
)


def _calculate_struct_design(inp: QuoteInput) -> QuoteResult:
    """구조설계용역견적서 산출 — xlsx 식 그대로 파이썬 재현."""
    # 1. 인.일 산출 — manhours_override가 있으면 그 값, 없으면 자동(ROUND 두 번)
    bm = baseline_manhours(inp.gross_floor_area)
    bm_rounded = int(_excel_round_half_up(bm, 0))
    if inp.manhours_override is not None:
        mh_total = int(inp.manhours_override)
    else:
        mh_total = int(
            _excel_round_half_up(
                bm_rounded * inp.type_rate * inp.structure_rate * inp.coefficient, 0
            )
        )

    # 2. 산출 — 단가는 사용자 선택 등급 우선, 없으면 default(고급기술자).
    direct_labor = mh_total * _resolve_rate(inp.engineer_grade, "고급기술자")
    # 직접경비: 새 동적 항목 list 우선, 없으면 legacy 필드 fallback
    if inp.direct_expense_items:
        direct_expense = sum(item.amount for item in inp.direct_expense_items)
    else:
        direct_expense = (
            inp.printing_fee + inp.survey_fee + 25_000 * inp.transport_persons
        )
    overhead = direct_labor * (inp.overhead_pct / 100)
    tech_fee = (direct_labor + overhead) * (inp.tech_fee_pct / 100)
    subtotal = direct_labor + overhead + tech_fee

    # 3. 당사 조정 (조정% 적용 + 직접경비 더함)
    adjusted = subtotal * (inp.adjustment_pct / 100) + direct_expense

    # 4. 절삭 — final_override 우선, 없으면 truncate_unit으로 절삭
    adjusted_int = int(_excel_round_half_up(adjusted, 0))
    if inp.final_override is not None:
        final_amount = int(inp.final_override)
        truncated = adjusted_int - final_amount  # 표시용 (음수 가능)
    else:
        unit = inp.truncate_unit if inp.truncate_unit > 0 else 1
        truncated = adjusted_int % unit
        final_amount = adjusted_int - truncated

    # 6. VAT (한국 부가세 10%) — final은 항상 공급가액. UI/xlsx 표시 분기는
    # vat_included 플래그가 결정하지만 계산값 자체는 항상 채워 응답에 일관성 유지.
    vat_amount = int(_excel_round_half_up(final_amount * 0.1, 0))
    final_with_vat = final_amount + vat_amount

    # 7. 평당 (P28, Q28)
    per_pyeong_area = inp.gross_floor_area / 3.3 if inp.gross_floor_area else 0
    per_pyeong = final_amount / per_pyeong_area if per_pyeong_area else 0

    return QuoteResult(
        manhours_baseline=bm,
        manhours_baseline_rounded=bm_rounded,
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


def _calculate_struct_review(inp: QuoteInput) -> QuoteResult:
    """구조검토용역견적서 산출.

    산식은 구조설계와 동일하나 인.일 자동 산출 흐름은 사용 안 함 — 사용자가
    manhours_override(인.일)를 직접 입력하는 모델. 미입력(None)이면 0으로
    처리해 자동 산출 트리거를 차단한다.
    """
    if inp.manhours_override is None:
        # manhours_override를 0으로 강제 → struct_design 자동 산출 분기 안 탐.
        # type_rate/structure_rate/coefficient도 산출에 영향 없음 (mh가 직접 0).
        return _calculate_struct_design(
            inp.model_copy(update={"manhours_override": 0})
        )
    return _calculate_struct_design(inp)
