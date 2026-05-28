"""건의사항 라우터 — create/list/update/delete 모두 mirror + outbox 기반.

권한 모델:
- 작성: 모든 인증 사용자 (작성자 = 본인 이름 자동)
- 진행상황 / 조치내용: 관리자/팀장만 수정 가능
- 그 외 (제목/내용): 본인이 작성한 글만 수정 가능
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
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
from app.security import get_current_user
from app.services.notion_outbox import enqueue
from app.services.sync import get_sync

logger = logging.getLogger("api.suggestions")
router = APIRouter(prefix="/suggestions", tags=["suggestions"])

_VALID_STATUSES = {"접수", "검토중", "완료", "반려"}
_LOCAL_ID_PREFIX = "local_suggestion_"

# PR-CN: 노션 DB의 title 컬럼명은 운영자가 자유 변경 가능 (default "Name", 한글 "제목" 등).
# create/update 시 잘못된 prop 이름 → 노션 400 → NotionApiError(502).
# 첫 호출 schema query로 동적 lookup + 모듈 단위 cache.
_title_prop_name: str | None = None


class SuggestionItem(BaseModel):
    id: str
    title: str = ""
    content: str = ""
    author: str = ""
    categories: list[str] = []  # PR-CO: 노션 "구분" multi_select
    status: str = "접수"
    resolution: str = ""
    created_time: str | None = None
    last_edited_time: str | None = None


class SuggestionListResponse(BaseModel):
    items: list[SuggestionItem]
    count: int


class SuggestionCreate(BaseModel):
    title: str
    content: str = ""
    categories: list[str] = []


class SuggestionUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    categories: list[str] | None = None  # 작성자/admin/team_lead 변경 가능
    status: str | None = None       # admin/team_lead만 변경 가능
    resolution: str | None = None   # admin/team_lead만 변경 가능


def _from_mirror(row: M.MirrorSuggestion) -> SuggestionItem:
    """PR-EX/3: mirror_suggestions row → SuggestionItem 변환.

    sync.py의 `_upsert_suggestion`이 _from_notion_page와 동일 매핑을 적용해
    저장하므로 frontend 응답 schema는 100% 일치.
    """
    return SuggestionItem(
        id=row.page_id,
        title=row.title or "",
        content=row.content or "",
        author=row.author or "",
        categories=list(row.categories or []),
        status=row.status or "접수",
        resolution=row.resolution or "",
        created_time=row.created_time.isoformat() if row.created_time else None,
        last_edited_time=row.last_edited_time.isoformat()
        if row.last_edited_time
        else None,
    )


def _title_prop_name_from_mirror() -> str:
    """mirror-only update에서 사용할 title prop 이름.

    운영 schema는 title="내용". create 경로가 schema lookup을 이미 수행했다면 그 값을 우선한다.
    """
    return _title_prop_name or "내용"


def _is_local_id(page_id: str) -> bool:
    return page_id.startswith(_LOCAL_ID_PREFIX)


def _active_create_outbox(db: Session, local_id: str) -> NotionOutbox | None:
    return db.execute(
        select(NotionOutbox)
        .where(
            NotionOutbox.aggregate_type == "suggestions",
            NotionOutbox.aggregate_id == local_id,
            NotionOutbox.op == OP_CREATE,
            NotionOutbox.status.in_([STATUS_PENDING, STATUS_PROCESSING, STATUS_RETRY]),
        )
        .order_by(NotionOutbox.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _resolve_suggestion_row(
    db: Session, page_id: str
) -> tuple[M.MirrorSuggestion, str]:
    """local id가 이미 Notion id로 확정된 경우까지 감안해 row를 찾는다."""
    row = db.get(M.MirrorSuggestion, page_id)
    if row is not None and not row.archived:
        return row, row.page_id
    if _is_local_id(page_id):
        real_id = db.execute(
            select(NotionOutbox.notion_page_id)
            .where(
                NotionOutbox.aggregate_type == "suggestions",
                NotionOutbox.aggregate_id == page_id,
                NotionOutbox.op == OP_CREATE,
                NotionOutbox.status == STATUS_SENT,
                NotionOutbox.notion_page_id.is_not(None),
            )
            .order_by(NotionOutbox.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if real_id:
            real_row = db.get(M.MirrorSuggestion, real_id)
            if real_row is not None and not real_row.archived:
                return real_row, real_row.page_id
    raise HTTPException(status_code=404, detail="건의사항을 찾을 수 없습니다")


@router.get("", response_model=SuggestionListResponse)
def list_suggestions(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SuggestionListResponse:
    """모든 건의사항 — 최신 작성순.

    PR-EX/3 (PR-CR 2순위 본격 해소): mirror_suggestions DB 조회로 전환.
    옛 notion.query_all 전량 fetch 패턴 폐기 — 5분 incremental cron이 mirror
    유지, write 흐름은 즉시 upsert(write-through).
    """
    stmt = (
        select(M.MirrorSuggestion)
        .where(M.MirrorSuggestion.archived.is_(False))
        .order_by(M.MirrorSuggestion.created_time.desc().nullslast())
    )
    rows = db.execute(stmt).scalars().all()
    items = [_from_mirror(r) for r in rows]
    return SuggestionListResponse(items=items, count=len(items))


@router.post("", response_model=SuggestionItem, status_code=status.HTTP_201_CREATED)
async def create_suggestion(
    body: SuggestionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SuggestionItem:
    if not body.title.strip():
        raise HTTPException(status_code=400, detail="제목을 입력하세요")
    title_prop = _title_prop_name_from_mirror()
    # PR-GK: create도 사용자 응답 path에서 Notion 직접 호출 제거. local id로 mirror에
    # 먼저 저장하고, outbox worker가 Notion create 성공 후 실제 page_id row로 치환한다.
    author_name = user.name or user.username
    title = body.title.strip()
    categories = [c for c in body.categories if c.strip()]
    props: dict[str, Any] = {
        title_prop: {"title": [{"text": {"content": title}}]},
        "방안": {"rich_text": [{"text": {"content": body.content}}]},
        # PR-CP: 운영 노션 "작성자"는 multi_select. 사용자명 1개 옵션으로.
        "작성자": {"multi_select": [{"name": author_name}]},
        "진행상황": {"status": {"name": "접수"}},
    }
    if categories:
        props["구분"] = {"multi_select": [{"name": c} for c in categories]}

    now = datetime.now(UTC)
    local_id = f"{_LOCAL_ID_PREFIX}{uuid4().hex}"
    row = M.MirrorSuggestion(
        page_id=local_id,
        title=title,
        content=body.content,
        author=author_name,
        categories=categories,
        status="접수",
        resolution="",
        created_time=now,
        last_edited_time=now,
        synced_at=now,
        archived=False,
    )
    db.add(row)
    enqueue(
        db,
        aggregate_type="suggestions",
        aggregate_id=local_id,
        op=OP_CREATE,
        payload=props,
        notion_page_id=None,
        dedupe_key=f"suggestions:{local_id}:create",
    )
    db.commit()
    db.refresh(row)
    return _from_mirror(row)


@router.patch("/{page_id}", response_model=SuggestionItem)
async def update_suggestion(
    page_id: str,
    body: SuggestionUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SuggestionItem:
    row, resolved_id = _resolve_suggestion_row(db, page_id)
    create_outbox = _active_create_outbox(db, resolved_id) if _is_local_id(resolved_id) else None
    if create_outbox is not None and create_outbox.status == STATUS_PROCESSING:
        raise HTTPException(
            status_code=409,
            detail="노션 생성 동기화 중입니다. 잠시 후 다시 시도하세요",
        )
    if _is_local_id(resolved_id) and create_outbox is None:
        raise HTTPException(
            status_code=409,
            detail="노션 생성 대기열을 찾을 수 없습니다. 새로고침 후 다시 시도하세요",
        )

    is_admin_or_lead = user.role in {"admin", "team_lead"}
    page_author = row.author or ""
    is_owner = (user.name or user.username) == page_author

    update_props: dict[str, Any] = {}

    # 제목/내용/구분 — 작성자 본인 또는 admin/team_lead 만 (PR-CO)
    if body.title is not None:
        if not (is_owner or is_admin_or_lead):
            raise HTTPException(
                status_code=403, detail="본인이 작성한 글만 수정 가능"
            )
        title_prop = _title_prop_name_from_mirror()
        update_props[title_prop] = {
            "title": [{"text": {"content": body.title.strip()}}]
        }
        row.title = body.title.strip()
    if body.content is not None:
        if not (is_owner or is_admin_or_lead):
            raise HTTPException(
                status_code=403, detail="본인이 작성한 글만 수정 가능"
            )
        update_props["방안"] = {"rich_text": [{"text": {"content": body.content}}]}
        row.content = body.content
    if body.categories is not None:
        if not (is_owner or is_admin_or_lead):
            raise HTTPException(
                status_code=403, detail="본인이 작성한 글만 수정 가능"
            )
        categories = [c for c in body.categories if c.strip()]
        update_props["구분"] = {"multi_select": [{"name": c} for c in categories]}
        row.categories = categories

    # 진행상황 / 조치내용 — admin/team_lead 전용
    if body.status is not None:
        if not is_admin_or_lead:
            raise HTTPException(
                status_code=403, detail="진행상황 변경은 관리자/팀장만 가능"
            )
        if body.status not in _VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"잘못된 상태: {body.status}")
        update_props["진행상황"] = {"status": {"name": body.status}}
        row.status = body.status
    if body.resolution is not None:
        if not is_admin_or_lead:
            raise HTTPException(
                status_code=403, detail="조치내용 작성은 관리자/팀장만 가능"
            )
        update_props["조치내용"] = {
            "rich_text": [{"text": {"content": body.resolution}}]
        }
        row.resolution = body.resolution

    if not update_props:
        raise HTTPException(status_code=400, detail="갱신할 필드가 없습니다")

    row.last_edited_time = datetime.now(UTC)
    if create_outbox is not None:
        create_outbox.payload = {**(create_outbox.payload or {}), **update_props}
    else:
        enqueue(
            db,
            aggregate_type="suggestions",
            aggregate_id=resolved_id,
            op=OP_UPDATE,
            payload=update_props,
            notion_page_id=resolved_id,
        )
    db.commit()
    return _from_mirror(row)


@router.delete("/{page_id}")
async def delete_suggestion(
    page_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """건의사항 archive — 작성자 본인 또는 admin/team_lead 만."""
    row, resolved_id = _resolve_suggestion_row(db, page_id)
    create_outbox = _active_create_outbox(db, resolved_id) if _is_local_id(resolved_id) else None
    if create_outbox is not None and create_outbox.status == STATUS_PROCESSING:
        raise HTTPException(
            status_code=409,
            detail="노션 생성 동기화 중입니다. 잠시 후 다시 시도하세요",
        )

    page_author = row.author or ""
    is_owner = (user.name or user.username) == page_author
    is_admin_or_lead = user.role in {"admin", "team_lead"}
    if not (is_owner or is_admin_or_lead):
        raise HTTPException(
            status_code=403, detail="본인 글만 삭제 가능 (관리자/팀장은 모두 가능)"
        )

    get_sync().archive_in_session(db, "suggestions", resolved_id)
    if create_outbox is not None:
        db.delete(create_outbox)
    elif not _is_local_id(resolved_id):
        enqueue(
            db,
            aggregate_type="suggestions",
            aggregate_id=resolved_id,
            op=OP_DELETE,
            payload={},
            notion_page_id=resolved_id,
        )
    db.commit()
    return {"status": "archived"}
