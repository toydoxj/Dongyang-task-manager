"""/api/cashflow — 수금 + 지출 통합 시계열 (mirror 조회)."""
from __future__ import annotations

from datetime import date as Date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import mirror as M
from app.models.auth import User
from app.models.cashflow import CashflowResponse
from app.security import get_current_user
from app.services.mirror_dto import cashflow_from_mirror

router = APIRouter(prefix="/cashflow", tags=["cashflow"])


def _parse_date(s: str | None) -> Date | None:
    if not s:
        return None
    try:
        return Date.fromisoformat(s)
    except ValueError:
        return None


@router.get("", response_model=CashflowResponse)
async def get_cashflow(
    project_id: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    flow: Literal["income", "expense", "all"] = Query(default="all"),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CashflowResponse:
    if flow not in ("income", "expense", "all"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="잘못된 flow 옵션"
        )

    stmt = select(M.MirrorCashflow).where(M.MirrorCashflow.archived.is_(False))
    if flow != "all":
        stmt = stmt.where(M.MirrorCashflow.kind == flow)
    if project_id:
        stmt = stmt.where(M.MirrorCashflow.project_ids.any(project_id))  # type: ignore[attr-defined]
    df = _parse_date(date_from)
    dt = _parse_date(date_to)
    if df:
        stmt = stmt.where(M.MirrorCashflow.date >= df)
    if dt:
        stmt = stmt.where(M.MirrorCashflow.date <= dt)
    stmt = stmt.order_by(M.MirrorCashflow.date.asc().nullslast())
    rows = db.execute(stmt).scalars().all()
    items = [cashflow_from_mirror(r) for r in rows]

    inc = sum(e.amount for e in items if e.type == "income")
    exp = sum(e.amount for e in items if e.type == "expense")
    return CashflowResponse(
        items=items,
        income_total=inc,
        expense_total=exp,
        net=inc - exp,
        count=len(items),
    )
