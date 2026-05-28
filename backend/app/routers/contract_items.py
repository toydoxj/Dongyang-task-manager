"""/api/contract-items — 프로젝트 계약 항목 CRUD (editor write).

공동수급/추가용역 — 1 프로젝트 N (발주처, 금액, 라벨) 항목.
read는 인증된 사용자 모두, 생성/수정/삭제는 admin/team_lead/manager(member 제외).
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import mirror as M
from app.models.auth import User
from app.models.contract_item import (
    ContractItem,
    ContractItemCreateRequest,
    ContractItemListResponse,
    ContractItemUpdateRequest,
    contract_item_create_props,
    contract_item_update_props,
)
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
from app.security import get_current_user, require_editor
from app.services.mirror_dto import contract_item_from_mirror
from app.services.notion_outbox import enqueue
from app.services.sync import get_sync

router = APIRouter(prefix="/contract-items", tags=["contract-items"])
_LOCAL_CONTRACT_ITEM_PREFIX = "local_contract_item_"


def _resolve_client_names(db: Session, items: list[ContractItem]) -> None:
    cids = {it.client_id for it in items if it.client_id}
    if not cids:
        return
    rows = db.execute(
        select(M.MirrorClient.page_id, M.MirrorClient.name).where(
            M.MirrorClient.page_id.in_(cids)
        )
    ).all()
    name_map: dict[str, str] = {pid: name for pid, name in rows}
    for it in items:
        if it.client_id:
            it.client_name = name_map.get(it.client_id, "")


def _is_local_contract_item_id(page_id: str) -> bool:
    return page_id.startswith(_LOCAL_CONTRACT_ITEM_PREFIX)


def _active_contract_item_create_outbox(
    db: Session, local_id: str
) -> NotionOutbox | None:
    return db.execute(
        select(NotionOutbox)
        .where(
            NotionOutbox.aggregate_type == "contract_items",
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


def _resolve_contract_item_row(
    db: Session, page_id: str
) -> tuple[M.MirrorContractItem, str]:
    """local id가 실제 Notion id로 확정된 뒤에도 계약 항목 row를 찾는다."""
    row = db.get(M.MirrorContractItem, page_id)
    if row is not None and not row.archived:
        return row, row.page_id
    if _is_local_contract_item_id(page_id):
        real_id = db.execute(
            select(NotionOutbox.notion_page_id)
            .where(
                NotionOutbox.aggregate_type == "contract_items",
                NotionOutbox.aggregate_id == page_id,
                NotionOutbox.op == OP_CREATE,
                NotionOutbox.status == STATUS_SENT,
                NotionOutbox.notion_page_id.is_not(None),
            )
            .order_by(NotionOutbox.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if real_id:
            real_row = db.get(M.MirrorContractItem, real_id)
            if real_row is not None and not real_row.archived:
                return real_row, real_row.page_id
    raise HTTPException(status_code=404, detail="계약 항목을 찾을 수 없습니다")


@router.get("", response_model=ContractItemListResponse)
def list_contract_items(
    project_id: str | None = Query(default=None),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContractItemListResponse:
    stmt = select(M.MirrorContractItem).where(
        M.MirrorContractItem.archived.is_(False)
    )
    if project_id:
        stmt = stmt.where(M.MirrorContractItem.project_id == project_id)
    stmt = stmt.order_by(
        M.MirrorContractItem.sort_order.asc(),
        M.MirrorContractItem.label.asc(),
    )
    rows = db.execute(stmt).scalars().all()
    items = [contract_item_from_mirror(r) for r in rows]
    _resolve_client_names(db, items)
    return ContractItemListResponse(items=items, count=len(items))


@router.post("", response_model=ContractItem, status_code=status.HTTP_201_CREATED)
async def create_contract_item(
    body: ContractItemCreateRequest,
    _user: User = Depends(require_editor),
    db: Session = Depends(get_db),
) -> ContractItem:
    if not body.project_id or not body.client_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="project_id, client_id 모두 필수",
        )
    props = contract_item_create_props(body)
    now = datetime.now(UTC)
    local_id = f"{_LOCAL_CONTRACT_ITEM_PREFIX}{uuid4().hex}"
    page_like = {
        "id": local_id,
        "properties": props,
        "created_time": now.isoformat(),
        "last_edited_time": now.isoformat(),
        "archived": False,
    }
    get_sync().upsert_in_session(db, "contract_items", page_like)
    enqueue(
        db,
        aggregate_type="contract_items",
        aggregate_id=local_id,
        op=OP_CREATE,
        payload=props,
        notion_page_id=None,
        dedupe_key=f"contract_items:{local_id}:create",
    )
    db.commit()
    item = ContractItem.from_notion_page(page_like)
    _resolve_client_names(db, [item])
    return item


@router.patch("/{page_id}", response_model=ContractItem)
async def update_contract_item(
    page_id: str,
    body: ContractItemUpdateRequest,
    _user: User = Depends(require_editor),
    db: Session = Depends(get_db),
) -> ContractItem:
    props = contract_item_update_props(body)
    if not props:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="변경할 필드가 없습니다"
        )
    prev_row, resolved_id = _resolve_contract_item_row(db, page_id)
    create_outbox = (
        _active_contract_item_create_outbox(db, resolved_id)
        if _is_local_contract_item_id(resolved_id)
        else None
    )
    if create_outbox is not None and create_outbox.status == STATUS_PROCESSING:
        raise HTTPException(
            status_code=409,
            detail="노션 생성 동기화 중입니다. 잠시 후 다시 시도하세요",
        )
    if _is_local_contract_item_id(resolved_id) and create_outbox is None:
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
    sync.upsert_in_session(db, "contract_items", page_like)
    if create_outbox is not None:
        create_outbox.payload = {**(create_outbox.payload or {}), **props}
    else:
        enqueue(
            db,
            aggregate_type="contract_items",
            aggregate_id=resolved_id,
            op=OP_UPDATE,
            payload=props,
            notion_page_id=resolved_id,
        )
    db.commit()
    item = ContractItem.from_notion_page(page_like)
    _resolve_client_names(db, [item])
    return item


@router.delete("/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contract_item(
    page_id: str,
    _user: User = Depends(require_editor),
    db: Session = Depends(get_db),
) -> None:
    """mirror archived 마킹 + outbox enqueue. 노션 archive는 drain이 background 처리.

    PR-FZ: 노션 동기 호출 제거 → mirror direct archive + outbox (tasks 패턴).
    이 항목을 참조하는 수금 row가 있어도 archive는 허용 (수금 흔적 보존).
    참조가 끊긴 row는 legacy 모드로 미수금 계산되도록 frontend가 fallback.
    """
    _prev_row, resolved_id = _resolve_contract_item_row(db, page_id)
    create_outbox = (
        _active_contract_item_create_outbox(db, resolved_id)
        if _is_local_contract_item_id(resolved_id)
        else None
    )
    if create_outbox is not None and create_outbox.status == STATUS_PROCESSING:
        raise HTTPException(
            status_code=409,
            detail="노션 생성 동기화 중입니다. 잠시 후 다시 시도하세요",
        )
    sync = get_sync()
    sync.archive_in_session(db, "contract_items", resolved_id)
    if create_outbox is not None:
        db.delete(create_outbox)
    elif not _is_local_contract_item_id(resolved_id):
        enqueue(
            db,
            aggregate_type="contract_items",
            aggregate_id=resolved_id,
            op=OP_DELETE,
            payload={},
            notion_page_id=resolved_id,
        )
    db.commit()
    return None
