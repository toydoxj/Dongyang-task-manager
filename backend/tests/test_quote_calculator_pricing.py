"""견적 산출 최종금액/VAT 처리 회귀 테스트."""
from __future__ import annotations

import pytest

from app.services.quote_calculator import QuoteInput, QuoteType, calculate


@pytest.mark.parametrize("quote_type", list(QuoteType))
def test_final_override_is_vat_included_total_when_checked(
    quote_type: QuoteType,
) -> None:
    """VAT 포함 체크 시 최종금액 직접입력값은 VAT 포함 총액으로 해석한다."""
    result = calculate(
        QuoteInput(
            quote_type=quote_type,
            final_override=11_000_000,
            vat_included=True,
        )
    )

    assert result.final == 10_000_000
    assert result.vat_amount == 1_000_000
    assert result.final_with_vat == 11_000_000


def test_final_override_remains_supply_amount_when_vat_not_checked() -> None:
    """VAT 포함 체크가 없으면 직접입력값은 기존처럼 공급가액이다."""
    result = calculate(
        QuoteInput(
            quote_type=QuoteType.STRUCT_DESIGN,
            final_override=10_000_000,
            vat_included=False,
        )
    )

    assert result.final == 10_000_000
    assert result.vat_amount == 1_000_000
    assert result.final_with_vat == 11_000_000
