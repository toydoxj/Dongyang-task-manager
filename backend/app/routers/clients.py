"""/api/clients — 협력업체(발주처) 목록 + CRUD."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import mirror as M
from app.models.auth import User
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
from app.security import get_current_user, require_admin
from app.services import notion_props as P
from app.services.notion_outbox import enqueue
from app.services.sync import get_sync

router = APIRouter(prefix="/clients", tags=["clients"])
_LOCAL_CLIENT_PREFIX = "local_client_"


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


def _client_from_props(page_id: str, props: dict) -> Client:
    return Client(
        id=page_id,
        name=P.title(props, "이름"),
        category=P.select_name(props, "구분"),
    )


def _is_local_client_id(page_id: str) -> bool:
    return page_id.startswith(_LOCAL_CLIENT_PREFIX)


def _active_client_create_outbox(db: Session, local_id: str) -> NotionOutbox | None:
    return db.execute(
        select(NotionOutbox)
        .where(
            NotionOutbox.aggregate_type == "clients",
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


def _resolve_client_row(db: Session, page_id: str) -> tuple[M.MirrorClient, str]:
    """local id가 실제 Notion id로 확정된 뒤에도 발주처 row를 찾는다."""
    row = db.get(M.MirrorClient, page_id)
    if row is not None and not row.archived:
        return row, row.page_id
    if _is_local_client_id(page_id):
        real_id = db.execute(
            select(NotionOutbox.notion_page_id)
            .where(
                NotionOutbox.aggregate_type == "clients",
                NotionOutbox.aggregate_id == page_id,
                NotionOutbox.op == OP_CREATE,
                NotionOutbox.status == STATUS_SENT,
                NotionOutbox.notion_page_id.is_not(None),
            )
            .order_by(NotionOutbox.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if real_id:
            real_row = db.get(M.MirrorClient, real_id)
            if real_row is not None and not real_row.archived:
                return real_row, real_row.page_id
    raise HTTPException(status_code=404, detail="발주처를 찾을 수 없습니다")


@router.get("", response_model=ClientListResponse)
def list_clients(
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
) -> Client:
    """발주처 local mirror row 생성 후 outbox로 Notion 생성을 예약.

    동일 이름(대소문자/공백 무시)이 mirror_clients에 이미 존재하면 그 row를
    그대로 반환 — 중복 페이지 생성 방지. 프론트 발주처 자동완성에서
    매칭 실패 시 호출해 relation_id를 즉시 확보하기 위한 진입점.
    """
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

    now = datetime.now(UTC)
    local_id = f"{_LOCAL_CLIENT_PREFIX}{uuid4().hex}"
    page_like = {
        "id": local_id,
        "properties": props,
        "created_time": now.isoformat(),
        "last_edited_time": now.isoformat(),
        "archived": False,
    }
    get_sync().upsert_in_session(db, "clients", page_like)
    enqueue(
        db,
        aggregate_type="clients",
        aggregate_id=local_id,
        op=OP_CREATE,
        payload=props,
        notion_page_id=None,
        dedupe_key=f"clients:{local_id}:create",
    )
    db.commit()
    return _client_from_props(local_id, props)


class ClientUpdateRequest(BaseModel):
    """None 필드는 변경 안 함."""

    name: str | None = None
    category: str | None = None


@router.patch("/{page_id}", response_model=Client)
async def update_client(
    page_id: str,
    body: ClientUpdateRequest,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Client:
    prev_row, resolved_id = _resolve_client_row(db, page_id)
    create_outbox = (
        _active_client_create_outbox(db, resolved_id)
        if _is_local_client_id(resolved_id)
        else None
    )
    if create_outbox is not None and create_outbox.status == STATUS_PROCESSING:
        raise HTTPException(
            status_code=409,
            detail="노션 생성 동기화 중입니다. 잠시 후 다시 시도하세요",
        )
    if _is_local_client_id(resolved_id) and create_outbox is None:
        raise HTTPException(
            status_code=409,
            detail="노션 생성 대기열을 찾을 수 없습니다. 새로고침 후 다시 시도하세요",
        )

    props: dict = {}
    if body.name is not None:
        new_name = body.name.strip()
        if not new_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="이름은 비울 수 없습니다"
            )
        # 중복 체크 (자기 자신 제외)
        dup = db.execute(
            select(M.MirrorClient)
            .where(
                M.MirrorClient.archived.is_(False),
                M.MirrorClient.page_id != resolved_id,
                func.lower(func.trim(M.MirrorClient.name)) == new_name.lower(),
            )
            .limit(1)
        ).scalar_one_or_none()
        if dup is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"동일한 이름의 발주처가 이미 존재합니다: {dup.name}",
            )
        props["이름"] = {"title": [{"text": {"content": new_name}}]}
    if body.category is not None:
        cat = body.category.strip()
        # 빈 문자열은 select clear 신호
        props["구분"] = {"select": None} if not cat else {"select": {"name": cat}}
    if not props:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="변경할 필드가 없습니다"
        )
    merged_props = {**(prev_row.properties or {}), **props}
    page_like = {
        "id": resolved_id,
        "properties": merged_props,
        "last_edited_time": datetime.now(UTC).isoformat(),
        "archived": False,
    }
    sync = get_sync()
    sync.upsert_in_session(db, "clients", page_like)
    if create_outbox is not None:
        create_outbox.payload = {**(create_outbox.payload or {}), **props}
    else:
        enqueue(
            db,
            aggregate_type="clients",
            aggregate_id=resolved_id,
            op=OP_UPDATE,
            payload=props,
            notion_page_id=resolved_id,
        )
    db.commit()
    return _client_from_props(resolved_id, merged_props)


@router.delete("/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_client(
    page_id: str,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    """발주처 페이지 archive(노션 휴지통). 기존 relation은 그대로 유지된다.

    삭제 전 사용처 검사: 활성 프로젝트의 발주처로 아직 참조 중이면 409.
    회계상 흔적은 보존하기 위함.

    PR-GA: 노션 동기 호출 제거 → mirror direct archive + outbox (PR-FZ 패턴).
    """
    _prev_row, resolved_id = _resolve_client_row(db, page_id)
    used_in_project = db.execute(
        select(M.MirrorProject.page_id)
        .where(
            M.MirrorProject.archived.is_(False),
            M.MirrorProject.client_relation_ids.contains([resolved_id]),  # type: ignore[attr-defined]
        )
        .limit(1)
    ).scalar_one_or_none()
    if used_in_project:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="아직 프로젝트에서 발주처로 사용 중입니다. 먼저 프로젝트의 발주처를 변경하세요.",
        )

    create_outbox = (
        _active_client_create_outbox(db, resolved_id)
        if _is_local_client_id(resolved_id)
        else None
    )
    if create_outbox is not None and create_outbox.status == STATUS_PROCESSING:
        raise HTTPException(
            status_code=409,
            detail="노션 생성 동기화 중입니다. 잠시 후 다시 시도하세요",
        )
    sync = get_sync()
    sync.archive_in_session(db, "clients", resolved_id)
    if create_outbox is not None:
        db.delete(create_outbox)
    elif not _is_local_client_id(resolved_id):
        enqueue(
            db,
            aggregate_type="clients",
            aggregate_id=resolved_id,
            op=OP_DELETE,
            payload={},
            notion_page_id=resolved_id,
        )
    db.commit()
    return None
