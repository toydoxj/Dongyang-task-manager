"""/api/contract-items — 프로젝트 계약 항목 CRUD (editor write).

공동수급/추가용역 — 1 프로젝트 N (발주처, 금액, 라벨) 항목.
read는 인증된 사용자 모두, 생성/수정/삭제는 admin/team_lead/manager(member 제외).
"""
from __future__ import annotations

import asyncio

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
from app.security import get_current_user, require_editor
from app.services.mirror_dto import contract_item_from_mirror
from app.services.notion import NotionService, get_notion
from app.services.sync import get_sync
from app.settings import get_settings

router = APIRouter(prefix="/contract-items", tags=["contract-items"])


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
    notion: NotionService = Depends(get_notion),
) -> ContractItem:
    db_id = get_settings().notion_db_contract_items
    if not db_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="NOTION_DB_CONTRACT_ITEMS 미설정",
        )
    if not body.project_id or not body.client_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="project_id, client_id 모두 필수",
        )
    page = await notion.create_page(db_id, contract_item_create_props(body))
    get_sync().upsert_page("contract_items", page)
    item = ContractItem.from_notion_page(page)
    _resolve_client_names(db, [item])
    return item


@router.patch("/{page_id}", response_model=ContractItem)
async def update_contract_item(
    page_id: str,
    body: ContractItemUpdateRequest,
    _user: User = Depends(require_editor),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> ContractItem:
    props = contract_item_update_props(body)
    if not props:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="변경할 필드가 없습니다"
        )
    page = await notion.update_page(page_id, properties=props)
    get_sync().upsert_page("contract_items", page)
    item = ContractItem.from_notion_page(page)
    _resolve_client_names(db, [item])
    return item


@router.delete("/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contract_item(
    page_id: str,
    _user: User = Depends(require_editor),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> None:
    """노션 archived + mirror archived 마킹.

    이 항목을 참조하는 수금 row가 있어도 archive는 허용 (수금 흔적 보존).
    참조가 끊긴 row는 legacy 모드로 미수금 계산되도록 frontend가 fallback.
    """
    await asyncio.to_thread(
        notion._client.pages.update, page_id=page_id, archived=True
    )
    db.query(M.MirrorContractItem).filter(
        M.MirrorContractItem.page_id == page_id
    ).update({"archived": True}, synchronize_session=False)
    db.commit()
    return None
