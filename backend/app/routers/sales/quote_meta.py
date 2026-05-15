"""견적서 메타 endpoint — 종류 enum, 라벨.

PR-CC (Phase 4-J 1단계): sales/__init__.py 분할 시작.
가장 작은 read-only endpoint(`GET /quote/types`)를 sub-router로 분리.
parent router prefix(`/api/sales`)는 sales/__init__.py가 그대로 유지.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.models.auth import User
from app.security import get_current_user
from app.services.quote_calculator import QuoteType

router = APIRouter()


@router.get("/quote/types")
def list_quote_types(
    _user: User = Depends(get_current_user),
) -> list[dict[str, str]]:
    """견적서 종류 enum + 한글 라벨. frontend select 옵션용.

    value/label 모두 한글 동일 (enum 값이 그대로 노션 select option name).
    """
    return [{"value": t.value, "label": t.value} for t in QuoteType]
