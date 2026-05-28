"""견적서 문서번호 분류 코드·순번 산정 회귀 테스트."""
from __future__ import annotations

from app.services.quote_calculator import QuoteType
from app.services.quote_code import (
    _CODE_MAP,
    _iter_quote_doc_numbers,
    _max_sequence_from_doc_numbers,
)


def test_quote_category_code_policy() -> None:
    """견적 종류별 문서번호 분류 코드는 운영 기준 01~05 그룹을 따른다."""
    assert _CODE_MAP == {
        QuoteType.STRUCT_DESIGN: "01",
        QuoteType.STRUCT_REVIEW: "01",
        QuoteType.PERF_SEISMIC: "01",
        QuoteType.FIELD_SUPPORT: "01",
        QuoteType.INSPECTION_REGULAR: "02",
        QuoteType.INSPECTION_DETAIL: "02",
        QuoteType.INSPECTION_DIAGNOSIS: "02",
        QuoteType.INSPECTION_BMA: "03",
        QuoteType.SEISMIC_EVAL: "04",
        QuoteType.REINFORCEMENT_DESIGN: "04",
        QuoteType.THIRD_PARTY_REVIEW: "04",
        QuoteType.SUPERVISION: "05",
        QuoteType.CUSTOM: "05",
    }


def test_sequence_checks_quote_form_data_docs_too() -> None:
    """다중 견적의 form 내부 doc_number도 다음 순번 max 계산에 포함한다."""
    docs = _iter_quote_doc_numbers(
        "26-01-001",
        {
            "forms": [
                {"doc_number": "26-01-003"},
                {"doc_number": "26-01-002A"},  # 옛 suffix 포함 표기도 순번으로 인식
                {"doc_number": "26-02-010"},
                {"doc_number": ""},
                {},
            ],
            "doc_number": "26-01-004",
        },
    )

    assert _max_sequence_from_doc_numbers(
        docs, year_yy=26, category_code="01"
    ) == 4
