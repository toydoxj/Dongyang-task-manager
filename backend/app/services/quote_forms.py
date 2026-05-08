"""영업 내 다중 견적서 list 다루는 helper (PR-M 시리즈).

기존 mirror_sales.quote_form_data 단일 schema:
    {"input": {...}, "result": {...}}

신규 list-wrapped schema:
    {"forms": [{"id": "...", "doc_number": "26-04-001", "suffix": "A",
                "input": {...}, "result": {...}}, ...]}

lazy wrapping — DB write는 list-wrapped로 하지만, read 시 옛 단일 schema도
허용 (자동 wrap). alembic migration 없이 점진 마이그레이션 가능.

문서번호 정책 (사용자 명시 2026-05-08):
- sequence는 분류별 독립 advisory lock (기존 정책 그대로)
- suffix는 영업 내 견적 인덱스 (1=A, 2=B, ..., 26=Z, 27=AA, 28=AB, ...)
- 표시: doc_number + suffix → "26-04-001A"
- 영업 내 두 번째 견적은 새 sequence + suffix B → "26-04-002B"
"""
from __future__ import annotations

import uuid
from typing import Any


def index_to_suffix(idx: int) -> str:
    """0=A, 1=B, ..., 25=Z, 26=AA, 27=AB, ... 영문 대문자 sequence.

    영업 내 견적이 26개 초과는 이론상이지만 안전하게 처리 (Excel column 패턴).
    """
    if idx < 0:
        raise ValueError("idx must be >= 0")
    chars = []
    while True:
        chars.append(chr(ord("A") + idx % 26))
        idx = idx // 26 - 1
        if idx < 0:
            break
    return "".join(reversed(chars))


def format_doc_full(doc_number: str, suffix: str) -> str:
    """문서번호 base + suffix → 표시 형식 ('26-04-001' + 'A' → '26-04-001A')."""
    return f"{doc_number}{suffix}" if doc_number else suffix


def normalize_quote_forms(
    form_data: dict[str, Any] | None,
    *,
    legacy_doc_number: str = "",
) -> list[dict[str, Any]]:
    """quote_form_data를 list[form] 형태로 정규화.

    - {"forms": [...]} 형태면 그대로
    - {"input", "result"} 단일 형태면 [{id, doc_number, suffix:"A", input, result}]로 wrap
    - None / 빈 dict면 []

    legacy_doc_number는 wrap 시 사용 — mirror_sales.quote_doc_number 컬럼값
    (옛 단일 견적의 문서번호).
    """
    if not form_data:
        return []
    forms = form_data.get("forms")
    if isinstance(forms, list):
        return forms
    # legacy 단일 schema → wrap
    if "input" in form_data:
        return [
            {
                "id": str(uuid.uuid4()),
                "doc_number": legacy_doc_number or "",
                "suffix": "A",
                "input": form_data.get("input") or {},
                "result": form_data.get("result") or {},
            }
        ]
    return []


def pack_quote_forms(forms: list[dict[str, Any]]) -> dict[str, Any]:
    """list[form] → quote_form_data wrapping schema (DB write용)."""
    return {"forms": forms}


def next_form_id() -> str:
    """신규 견적 추가 시 부여할 고유 id (uuid4 hex)."""
    return str(uuid.uuid4())
