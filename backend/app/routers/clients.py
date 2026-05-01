"""/api/clients — 협력업체(발주처) 목록 + 신규 등록."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import mirror as M
from app.models.auth import User
from app.security import get_current_user
from app.services import notion_props as P
from app.services.notion import NotionService, get_notion
from app.services.sync import get_sync
from app.settings import get_settings

router = APIRouter(prefix="/clients", tags=["clients"])


class Client(BaseModel):
    id: str
    name: str
    category: str = ""


class ClientListResponse(BaseModel):
    items: list[Client]
    count: int


class ClientCreateRequest(BaseModel):
    """발주처 등록 요청. 이름만 필수, 구분은 선택."""

    name: str
    category: str = ""  # 노션 '구분' select (건축사무소/시공사/감리/...)


@router.get("", response_model=ClientListResponse)
async def list_clients(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ClientListResponse:
    stmt = (
        select(M.MirrorClient)
        .where(M.MirrorClient.archived.is_(False))
        .order_by(M.MirrorClient.name.asc())
    )
    rows = db.execute(stmt).scalars().all()
    items = [
        Client(id=r.page_id, name=r.name, category=r.category) for r in rows
    ]
    return ClientListResponse(items=items, count=len(items))


@router.post("", response_model=Client, status_code=status.HTTP_201_CREATED)
async def create_client(
    body: ClientCreateRequest,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> Client:
    """발주처 DB(노션)에 새 페이지 생성 후 mirror에 즉시 반영.

    동일 이름(대소문자/공백 무시)이 mirror_clients에 이미 존재하면 그 row를
    그대로 반환 — 중복 페이지 생성 방지. 프론트 발주처 자동완성에서
    매칭 실패 시 호출해 relation_id를 즉시 확보하기 위한 진입점.
    """
    db_id = get_settings().notion_db_clients
    if not db_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="NOTION_DB_CLIENTS 미설정",
        )

    name = (body.name or "").strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="이름 필수"
        )

    existing = db.execute(
        select(M.MirrorClient)
        .where(
            M.MirrorClient.archived.is_(False),
            func.lower(func.trim(M.MirrorClient.name)) == name.lower(),
        )
        .limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        return Client(
            id=existing.page_id,
            name=existing.name,
            category=existing.category,
        )

    props: dict = {"이름": {"title": [{"text": {"content": name}}]}}
    category = (body.category or "").strip()
    if category:
        props["구분"] = {"select": {"name": category}}

    page = await notion.create_page(db_id, props)
    get_sync().upsert_page("clients", page)

    # 응답은 mirror가 아닌 노션 page 기준 — sync race 방지
    page_props = page.get("properties", {})
    actual_name = P.title(page_props, "이름") or name
    actual_category = P.select_name(page_props, "구분")
    return Client(
        id=page.get("id", ""), name=actual_name, category=actual_category
    )
