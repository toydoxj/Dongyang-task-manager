"""/api/clients — 협력업체 목록 (mirror 조회)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import mirror as M
from app.models.auth import User
from app.security import get_current_user

router = APIRouter(prefix="/clients", tags=["clients"])


class Client(BaseModel):
    id: str
    name: str
    category: str = ""


class ClientListResponse(BaseModel):
    items: list[Client]
    count: int


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
