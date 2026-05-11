"""/api/cashflow — 수금 + 지출 통합 시계열 (mirror 조회) + 수금 CRUD (admin/manager)."""
from __future__ import annotations

import asyncio
from datetime import date as Date
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import mirror as M
from app.models.auth import User
from app.models.cashflow import CashflowEntry, CashflowResponse
from app.security import get_current_user, require_admin_or_manager
from app.services.mirror_dto import cashflow_from_mirror
from app.services.notion import NotionService, get_notion
from app.services.sync import get_sync
from app.settings import get_settings

router = APIRouter(prefix="/cashflow", tags=["cashflow"])


def _parse_date(s: str | None) -> Date | None:
    if not s:
        return None
    try:
        return Date.fromisoformat(s)
    except ValueError:
        return None


def _resolve_payer_names(db: Session, items: list[CashflowEntry]) -> None:
    payer_ids: set[str] = {rid for e in items for rid in e.payer_relation_ids if rid}
    if not payer_ids:
        return
    rows = db.execute(
        select(M.MirrorClient.page_id, M.MirrorClient.name).where(
            M.MirrorClient.page_id.in_(payer_ids)
        )
    ).all()
    name_map: dict[str, str] = {pid: name for pid, name in rows}
    for e in items:
        if e.payer_relation_ids:
            e.payer_names = [
                name_map.get(rid, "")
                for rid in e.payer_relation_ids
                if name_map.get(rid)
            ]


def _resolve_contract_item_labels(
    db: Session, items: list[CashflowEntry]
) -> None:
    ci_ids: set[str] = {e.contract_item_id for e in items if e.contract_item_id}
    if not ci_ids:
        return
    rows = db.execute(
        select(M.MirrorContractItem.page_id, M.MirrorContractItem.label).where(
            M.MirrorContractItem.page_id.in_(ci_ids)
        )
    ).all()
    label_map: dict[str, str] = {pid: label for pid, label in rows}
    for e in items:
        if e.contract_item_id:
            e.contract_item_label = label_map.get(e.contract_item_id) or None


@router.get("", response_model=CashflowResponse)
def get_cashflow(
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
        # contains(@>) 형태 — ARRAY GIN 인덱스 활용. .any() 는 GIN 미적용.
        stmt = stmt.where(M.MirrorCashflow.project_ids.contains([project_id]))  # type: ignore[attr-defined]
    df = _parse_date(date_from)
    dt = _parse_date(date_to)
    if df:
        stmt = stmt.where(M.MirrorCashflow.date >= df)
    if dt:
        stmt = stmt.where(M.MirrorCashflow.date <= dt)
    stmt = stmt.order_by(M.MirrorCashflow.date.asc().nullslast())
    rows = db.execute(stmt).scalars().all()
    items = [cashflow_from_mirror(r) for r in rows]

    _resolve_payer_names(db, items)
    _resolve_contract_item_labels(db, items)

    inc = sum(e.amount for e in items if e.type == "income")
    exp = sum(e.amount for e in items if e.type == "expense")
    return CashflowResponse(
        items=items,
        income_total=inc,
        expense_total=exp,
        net=inc - exp,
        count=len(items),
    )


# ── 수금 CRUD (admin only) ──────────────────────────────────────────────


class IncomeCreateRequest(BaseModel):
    date: str  # YYYY-MM-DD, 필수
    amount: float
    round_no: int | None = None
    project_ids: list[str] = []
    payer_relation_ids: list[str] = []
    contract_item_id: str | None = None  # 분담 항목 매칭 (없으면 legacy)
    note: str = ""


class IncomeUpdateRequest(BaseModel):
    """None 필드는 변경 안 함. 빈 문자열은 'clear' 신호 (date에 한해)."""

    date: str | None = None
    amount: float | None = None
    round_no: int | None = None
    project_ids: list[str] | None = None
    payer_relation_ids: list[str] | None = None
    contract_item_id: str | None = None
    note: str | None = None


def _income_create_props(req: IncomeCreateRequest) -> dict[str, Any]:
    props: dict[str, Any] = {
        "수금일": {"date": {"start": req.date, "end": None}},
        "수금액(원)": {"number": req.amount},
    }
    if req.round_no is not None:
        props["회차"] = {"number": req.round_no}
    if req.project_ids:
        props["(주)동양구조 업무관리 - 프로젝트"] = {
            "relation": [{"id": pid} for pid in req.project_ids]
        }
    # 발주처는 contract_item으로 결정 — 별도 '실지급' 컬럼 매핑 없음
    if req.contract_item_id:
        props["계약항목"] = {"relation": [{"id": req.contract_item_id}]}
    if req.note:
        props["비고"] = {"rich_text": [{"text": {"content": req.note}}]}
    return props


def _income_update_props(req: IncomeUpdateRequest) -> dict[str, Any]:
    props: dict[str, Any] = {}
    if req.date is not None:
        props["수금일"] = (
            {"date": None}
            if req.date == ""
            else {"date": {"start": req.date, "end": None}}
        )
    if req.amount is not None:
        props["수금액(원)"] = {"number": req.amount}
    if req.round_no is not None:
        props["회차"] = {"number": req.round_no}
    if req.project_ids is not None:
        props["(주)동양구조 업무관리 - 프로젝트"] = {
            "relation": [{"id": pid} for pid in req.project_ids]
        }
    if req.contract_item_id is not None:
        props["계약항목"] = (
            {"relation": []}
            if req.contract_item_id == ""
            else {"relation": [{"id": req.contract_item_id}]}
        )
    if req.note is not None:
        props["비고"] = {"rich_text": [{"text": {"content": req.note}}]}
    return props


@router.post("/incomes", response_model=CashflowEntry)
async def create_income(
    body: IncomeCreateRequest,
    _user: User = Depends(require_admin_or_manager),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> CashflowEntry:
    db_id = get_settings().notion_db_cashflow
    if not db_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="NOTION_DB_CASHFLOW 미설정",
        )
    if not body.date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="수금일 필수"
        )
    page = await notion.create_page(db_id, _income_create_props(body))
    get_sync().upsert_page("cashflow", page)
    entry = CashflowEntry.from_income_page(page)
    _resolve_payer_names(db, [entry])
    _resolve_contract_item_labels(db, [entry])
    return entry


@router.patch("/incomes/{page_id}", response_model=CashflowEntry)
async def update_income(
    page_id: str,
    body: IncomeUpdateRequest,
    _user: User = Depends(require_admin_or_manager),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> CashflowEntry:
    props = _income_update_props(body)
    if not props:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="변경할 필드가 없습니다"
        )
    page = await notion.update_page(page_id, properties=props)
    get_sync().upsert_page("cashflow", page)
    entry = CashflowEntry.from_income_page(page)
    _resolve_payer_names(db, [entry])
    _resolve_contract_item_labels(db, [entry])
    return entry


@router.delete("/incomes/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_income(
    page_id: str,
    _user: User = Depends(require_admin_or_manager),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> None:
    """노션 페이지 archive(in_trash) + mirror archive 마킹."""
    await asyncio.to_thread(
        notion._client.pages.update, page_id=page_id, archived=True
    )
    db.query(M.MirrorCashflow).filter(M.MirrorCashflow.page_id == page_id).update(
        {"archived": True}, synchronize_session=False
    )
    db.commit()
    return None
