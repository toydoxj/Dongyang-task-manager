"""/api/cashflow — 수금 + 지출 통합 시계열 (mirror 조회) + 수금 CRUD (admin/manager)."""
from __future__ import annotations

from datetime import UTC, datetime
from datetime import date as Date
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import literal, select, union_all
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import mirror as M
from app.models.auth import User
from app.models.cashflow import CashflowEntry, CashflowResponse
from app.models.notion_outbox import (
    OP_CREATE,
    OP_DELETE,
    OP_UPDATE,
    STATUS_PENDING,
    STATUS_PROCESSING,
    STATUS_RETRY,
    STATUS_SENT,
    NotionOutbox,
)
from app.security import get_current_user, require_admin_or_manager
from app.services.mirror_dto import cashflow_from_mirror
from app.services.notion_outbox import enqueue
from app.services.sync import get_sync

router = APIRouter(prefix="/cashflow", tags=["cashflow"])
_LOCAL_INCOME_PREFIX = "local_cashflow_income_"


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


def _resolve_cashflow_labels_batch(
    db: Session, items: list[CashflowEntry]
) -> None:
    """PR-ER (PR-CR 진단 2순위): list 경로용 — payer + contract_item label을
    `UNION ALL` 1 round-trip으로 조회. 단일 entry endpoint(POST/PATCH)는 기존
    _resolve_* 두 함수 유지 (item 1개라 효과 없음, 단순성 우선).
    """
    payer_ids: set[str] = {rid for e in items for rid in e.payer_relation_ids if rid}
    ci_ids: set[str] = {e.contract_item_id for e in items if e.contract_item_id}
    if not payer_ids and not ci_ids:
        return
    queries = []
    if payer_ids:
        queries.append(
            select(
                literal("c").label("kind"),
                M.MirrorClient.page_id.label("pid"),
                M.MirrorClient.name.label("label"),
            ).where(M.MirrorClient.page_id.in_(payer_ids))
        )
    if ci_ids:
        queries.append(
            select(
                literal("ci").label("kind"),
                M.MirrorContractItem.page_id.label("pid"),
                M.MirrorContractItem.label.label("label"),
            ).where(M.MirrorContractItem.page_id.in_(ci_ids))
        )
    stmt = queries[0] if len(queries) == 1 else union_all(*queries)
    rows = db.execute(stmt).all()
    name_map: dict[str, str] = {}
    label_map: dict[str, str] = {}
    for kind, pid, label in rows:
        if kind == "c":
            name_map[pid] = label
        else:
            label_map[pid] = label
    for e in items:
        if e.payer_relation_ids:
            e.payer_names = [
                name_map[rid] for rid in e.payer_relation_ids if rid in name_map
            ]
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

    # PR-ER: payer + contract_item label batch — UNION ALL 1 round-trip.
    _resolve_cashflow_labels_batch(db, items)

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


def _is_local_income_id(page_id: str) -> bool:
    return page_id.startswith(_LOCAL_INCOME_PREFIX)


def _active_income_create_outbox(
    db: Session, local_id: str
) -> NotionOutbox | None:
    return db.execute(
        select(NotionOutbox)
        .where(
            NotionOutbox.aggregate_type == "cashflow",
            NotionOutbox.aggregate_id == local_id,
            NotionOutbox.op == OP_CREATE,
            NotionOutbox.status.in_([
                STATUS_PENDING,
                STATUS_PROCESSING,
                STATUS_RETRY,
            ]),
        )
        .order_by(NotionOutbox.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _resolve_income_row(
    db: Session, page_id: str
) -> tuple[M.MirrorCashflow, str]:
    """local id가 실제 Notion id로 확정된 뒤에도 수금 row를 찾는다."""
    row = db.get(M.MirrorCashflow, page_id)
    if row is not None and not row.archived:
        return row, row.page_id
    if _is_local_income_id(page_id):
        real_id = db.execute(
            select(NotionOutbox.notion_page_id)
            .where(
                NotionOutbox.aggregate_type == "cashflow",
                NotionOutbox.aggregate_id == page_id,
                NotionOutbox.op == OP_CREATE,
                NotionOutbox.status == STATUS_SENT,
                NotionOutbox.notion_page_id.is_not(None),
            )
            .order_by(NotionOutbox.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if real_id:
            real_row = db.get(M.MirrorCashflow, real_id)
            if real_row is not None and not real_row.archived:
                return real_row, real_row.page_id
    raise HTTPException(status_code=404, detail="수금 항목을 찾을 수 없습니다")


@router.post("/incomes", response_model=CashflowEntry)
async def create_income(
    body: IncomeCreateRequest,
    _user: User = Depends(require_admin_or_manager),
    db: Session = Depends(get_db),
) -> CashflowEntry:
    if not body.date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="수금일 필수"
        )
    props = _income_create_props(body)
    now = datetime.now(UTC)
    local_id = f"{_LOCAL_INCOME_PREFIX}{uuid4().hex}"
    page_like = {
        "id": local_id,
        "properties": props,
        "created_time": now.isoformat(),
        "last_edited_time": now.isoformat(),
        "archived": False,
    }
    get_sync().upsert_in_session(db, "cashflow", page_like)
    enqueue(
        db,
        aggregate_type="cashflow",
        aggregate_id=local_id,
        op=OP_CREATE,
        payload=props,
        notion_page_id=None,
        dedupe_key=f"cashflow:{local_id}:create",
    )
    db.commit()
    entry = CashflowEntry.from_income_page(page_like)
    _resolve_payer_names(db, [entry])
    _resolve_contract_item_labels(db, [entry])
    return entry


@router.patch("/incomes/{page_id}", response_model=CashflowEntry)
async def update_income(
    page_id: str,
    body: IncomeUpdateRequest,
    _user: User = Depends(require_admin_or_manager),
    db: Session = Depends(get_db),
) -> CashflowEntry:
    props = _income_update_props(body)
    if not props:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="변경할 필드가 없습니다"
        )
    prev_row, resolved_id = _resolve_income_row(db, page_id)
    create_outbox = (
        _active_income_create_outbox(db, resolved_id)
        if _is_local_income_id(resolved_id)
        else None
    )
    if create_outbox is not None and create_outbox.status == STATUS_PROCESSING:
        raise HTTPException(
            status_code=409,
            detail="노션 생성 동기화 중입니다. 잠시 후 다시 시도하세요",
        )
    if _is_local_income_id(resolved_id) and create_outbox is None:
        raise HTTPException(
            status_code=409,
            detail="노션 생성 대기열을 찾을 수 없습니다. 새로고침 후 다시 시도하세요",
        )
    merged_props = {**(prev_row.properties or {}), **props}
    page_like = {
        "id": resolved_id,
        "properties": merged_props,
        "last_edited_time": datetime.now(UTC).isoformat(),
        "archived": False,
    }
    sync = get_sync()
    sync.upsert_in_session(db, "cashflow", page_like)
    if create_outbox is not None:
        create_outbox.payload = {**(create_outbox.payload or {}), **props}
    else:
        enqueue(
            db,
            aggregate_type="cashflow",
            aggregate_id=resolved_id,
            op=OP_UPDATE,
            payload=props,
            notion_page_id=resolved_id,
        )
    db.commit()
    entry = CashflowEntry.from_income_page(page_like)
    _resolve_payer_names(db, [entry])
    _resolve_contract_item_labels(db, [entry])
    return entry


@router.delete("/incomes/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_income(
    page_id: str,
    _user: User = Depends(require_admin_or_manager),
    db: Session = Depends(get_db),
) -> None:
    """mirror archive 마킹 + outbox enqueue. 노션 archive는 drain이 background 처리.

    PR-GA: 노션 동기 호출 제거 → mirror direct archive + outbox (PR-FZ 패턴).
    """
    _prev_row, resolved_id = _resolve_income_row(db, page_id)
    create_outbox = (
        _active_income_create_outbox(db, resolved_id)
        if _is_local_income_id(resolved_id)
        else None
    )
    if create_outbox is not None and create_outbox.status == STATUS_PROCESSING:
        raise HTTPException(
            status_code=409,
            detail="노션 생성 동기화 중입니다. 잠시 후 다시 시도하세요",
        )
    sync = get_sync()
    sync.archive_in_session(db, "cashflow", resolved_id)
    if create_outbox is not None:
        db.delete(create_outbox)
    elif not _is_local_income_id(resolved_id):
        enqueue(
            db,
            aggregate_type="cashflow",
            aggregate_id=resolved_id,
            op=OP_DELETE,
            payload={},
            notion_page_id=resolved_id,
        )
    db.commit()
    return None
