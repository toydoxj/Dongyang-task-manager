"""/api/clients — 협력업체(발주처/시공사 등) 목록."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.models.auth import User
from app.security import get_current_user
from app.services import notion_props as P
from app.services.notion import NotionService, get_notion
from pydantic import BaseModel

router = APIRouter(prefix="/clients", tags=["clients"])

_CLIENT_DB_ID = "307e84986c8680f197eed98407eabf84"


class Client(BaseModel):
    id: str
    name: str
    category: str = ""  # 구분: 건축사무소/시공사/감리/협력 구조사무소/...


class ClientListResponse(BaseModel):
    items: list[Client]
    count: int


@router.get("", response_model=ClientListResponse)
async def list_clients(
    _user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> ClientListResponse:
    pages = await notion.query_all(_CLIENT_DB_ID)
    items: list[Client] = []
    for p in pages:
        props = p.get("properties", {})
        # title property 자동 탐지 (스키마 변경 robust)
        name = ""
        for prop in props.values():
            if prop.get("type") == "title":
                arr = prop.get("title") or []
                name = arr[0].get("plain_text", "") if arr else ""
                break
        items.append(
            Client(
                id=p.get("id", ""),
                name=name,
                category=P.select_name(props, "구분"),
            )
        )
    items.sort(key=lambda c: c.name)
    return ClientListResponse(items=items, count=len(items))
