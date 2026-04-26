"""/api/cashflow — 수금 + 지출 통합 시계열 (시각화용)."""
from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.models.auth import User
from app.models.cashflow import CashflowEntry, CashflowResponse
from app.security import get_current_user
from app.services.notion import NotionService, get_notion
from app.settings import get_settings

router = APIRouter(prefix="/cashflow", tags=["cashflow"])


def _date_range_filter(
    prop_name: str, date_from: str | None, date_to: str | None
) -> dict[str, Any] | None:
    clauses: list[dict[str, Any]] = []
    if date_from:
        clauses.append({"property": prop_name, "date": {"on_or_after": date_from}})
    if date_to:
        clauses.append({"property": prop_name, "date": {"on_or_before": date_to}})
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"and": clauses}


def _project_filter(prop_name: str, project_id: str | None) -> dict[str, Any] | None:
    if not project_id:
        return None
    return {"property": prop_name, "relation": {"contains": project_id}}


def _combine_and(*clauses: dict[str, Any] | None) -> dict[str, Any] | None:
    valid = [c for c in clauses if c is not None]
    if not valid:
        return None
    if len(valid) == 1:
        return valid[0]
    return {"and": valid}


async def _fetch_incomes(
    notion: NotionService,
    db_id: str,
    project_id: str | None,
    date_from: str | None,
    date_to: str | None,
) -> list[CashflowEntry]:
    if not db_id:
        return []
    filt = _combine_and(
        _project_filter("(주)동양구조 업무관리 - 프로젝트", project_id),
        _date_range_filter("수금일", date_from, date_to),
    )
    pages = await notion.query_all(
        db_id, filter=filt, sorts=[{"property": "수금일", "direction": "ascending"}]
    )
    return [CashflowEntry.from_income_page(p) for p in pages]


async def _fetch_expenses(
    notion: NotionService,
    db_id: str,
    project_id: str | None,
    date_from: str | None,
    date_to: str | None,
) -> list[CashflowEntry]:
    if not db_id:
        return []
    filt = _combine_and(
        _project_filter("프로젝트", project_id),
        _date_range_filter("지출일", date_from, date_to),
    )
    pages = await notion.query_all(
        db_id, filter=filt, sorts=[{"property": "지출일", "direction": "ascending"}]
    )
    return [CashflowEntry.from_expense_page(p) for p in pages]


@router.get("", response_model=CashflowResponse)
async def get_cashflow(
    project_id: str | None = Query(default=None, description="프로젝트 page_id 로 필터"),
    date_from: str | None = Query(default=None, description="ISO YYYY-MM-DD"),
    date_to: str | None = Query(default=None, description="ISO YYYY-MM-DD"),
    flow: Literal["income", "expense", "all"] = Query(default="all"),
    _user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> CashflowResponse:
    s = get_settings()

    coros = []
    if flow in ("income", "all"):
        coros.append(
            _fetch_incomes(notion, s.notion_db_cashflow, project_id, date_from, date_to)
        )
    if flow in ("expense", "all"):
        coros.append(
            _fetch_expenses(notion, s.notion_db_expense, project_id, date_from, date_to)
        )
    if not coros:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="잘못된 flow 옵션"
        )

    results = await asyncio.gather(*coros)
    items: list[CashflowEntry] = [e for sub in results for e in sub]

    # 날짜순 정렬 (None은 뒤로)
    items.sort(key=lambda e: (e.date is None, e.date or ""))

    inc = sum(e.amount for e in items if e.type == "income")
    exp = sum(e.amount for e in items if e.type == "expense")
    return CashflowResponse(
        items=items,
        income_total=inc,
        expense_total=exp,
        net=inc - exp,
        count=len(items),
    )
