"""견적서 메타 endpoint — 종류 enum, 산출 미리보기.

PR-CC (Phase 4-J 1단계): `GET /quote/types` 분리.
PR-CF (Phase 4-J 4단계): `POST /quote/preview` 추가 — 견적 산출 read-only.

parent router prefix(`/api/sales`)는 sales/__init__.py가 그대로 유지.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.models.auth import User
from app.security import get_current_user
from app.services.quote_calculator import QuoteInput, QuoteResult, QuoteType, calculate

router = APIRouter()


@router.get("/quote/types")
def list_quote_types(
    _user: User = Depends(get_current_user),
) -> list[dict[str, str]]:
    """견적서 종류 enum + 한글 라벨. frontend select 옵션용.

    value/label 모두 한글 동일 (enum 값이 그대로 노션 select option name).
    """
    return [{"value": t.value, "label": t.value} for t in QuoteType]


@router.post("/quote/preview", response_model=QuoteResult)
def preview_quote(
    body: QuoteInput,
    _user: User = Depends(get_current_user),
) -> QuoteResult:
    """견적서 입력 → 산출 결과만 반환 (저장 X). 프론트의 실시간 산출 패널용."""
    return calculate(body)
