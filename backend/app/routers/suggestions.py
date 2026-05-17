"""건의사항 라우터 — 노션 DB 직접 read/write (mirror 없음, 작은 데이터).

권한 모델:
- 작성: 모든 인증 사용자 (작성자 = 본인 이름 자동)
- 진행상황 / 조치내용: 관리자/팀장만 수정 가능
- 그 외 (제목/내용): 본인이 작성한 글만 수정 가능
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.exceptions import NotFoundError
from app.models import mirror as M
from app.models.auth import User
from app.security import get_current_user
from app.services import notion_props as P
from app.services.notion import NotionService, get_notion
from app.services.sync import get_sync
from app.settings import get_settings

logger = logging.getLogger("api.suggestions")
router = APIRouter(prefix="/suggestions", tags=["suggestions"])

_VALID_STATUSES = {"접수", "검토중", "완료", "반려"}

# PR-CN: 노션 DB의 title 컬럼명은 운영자가 자유 변경 가능 (default "Name", 한글 "제목" 등).
# create/update 시 잘못된 prop 이름 → 노션 400 → NotionApiError(502).
# 첫 호출 schema query로 동적 lookup + 모듈 단위 cache.
_title_prop_name: str | None = None


async def _get_title_prop_name(notion: NotionService) -> str:
    """건의사항 DB의 title type property 이름. 첫 호출 schema query, 이후 cache."""
    global _title_prop_name
    if _title_prop_name is not None:
        return _title_prop_name
    try:
        ds = await notion.get_data_source(_db_id())
    except Exception as e:  # noqa: BLE001
        logger.warning("suggestions title prop 탐지 실패 — `제목` fallback: %s", e)
        return "제목"
    for name, spec in (ds.get("properties") or {}).items():
        if isinstance(spec, dict) and spec.get("type") == "title":
            _title_prop_name = name
            return name
    logger.warning("suggestions DB에 title type property 없음 — `제목` fallback")
    return "제목"


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


def _from_notion_page(page: dict[str, Any]) -> SuggestionItem:
    """PR-CO: 운영 노션 schema 매핑 — title="내용"(title), content="방안"(rich_text),
    categories="구분"(multi_select), status="진행상황"(status type), resolution="조치내용".
    """
    props = page.get("properties", {})
    # title 컬럼명은 dynamic이지만 read는 "type=title"인 첫 컬럼만 잡으면 됨 (helper 동일).
    # 운영은 title 컬럼명이 "내용"이라 기존 P.title("제목")이 빈 string 반환 → 502는 write에서만.
    # read는 안전하게 dynamic lookup 후 한 번 찾아두면 OK이지만 sync 함수라 일단 운영 컬럼명 직접 매핑.
    title_text = P.title(props, "내용") or P.title(props, "제목") or P.title(props, "Name")
    # PR-CP: "작성자"는 운영 노션에서 multi_select type. 첫 옵션이 본인 이름.
    # 호환: 옛 rich_text type일 가능성도 처리 (둘 중 채워진 것 우선).
    author_list = P.multi_select_names(props, "작성자")
    author_text = author_list[0] if author_list else P.rich_text(props, "작성자")
    return SuggestionItem(
        id=page.get("id", ""),
        title=title_text,
        content=P.rich_text(props, "방안"),
        author=author_text,
        categories=P.multi_select_names(props, "구분"),
        status=P.status_name(props, "진행상황") or P.select_name(props, "진행상황") or "접수",
        resolution=P.rich_text(props, "조치내용"),
        created_time=page.get("created_time"),
        last_edited_time=page.get("last_edited_time"),
    )


def _db_id() -> str:
    db_id = get_settings().notion_db_suggestions
    if not db_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="NOTION_DB_SUGGESTIONS 미설정",
        )
    return db_id


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
    notion: NotionService = Depends(get_notion),
) -> SuggestionItem:
    if not body.title.strip():
        raise HTTPException(status_code=400, detail="제목을 입력하세요")
    title_prop = await _get_title_prop_name(notion)
    # PR-CO: 운영 노션 schema 매핑 — title 컬럼은 "내용"(dynamic), 본문은 "방안",
    # 진행상황은 status type. title_prop과 "방안"이 충돌하지 않도록 분리.
    author_name = user.name or user.username
    props: dict[str, Any] = {
        title_prop: {"title": [{"text": {"content": body.title.strip()}}]},
        "방안": {"rich_text": [{"text": {"content": body.content}}]},
        # PR-CP: 운영 노션 "작성자"는 multi_select. 사용자명 1개 옵션으로.
        "작성자": {"multi_select": [{"name": author_name}]},
        "진행상황": {"status": {"name": "접수"}},
    }
    if body.categories:
        props["구분"] = {
            "multi_select": [{"name": c} for c in body.categories if c.strip()]
        }
    page = await notion.create_page(_db_id(), props)
    # PR-EX/3: write-through — mirror 즉시 upsert (5분 sync 기다리지 않음)
    try:
        get_sync().upsert_page("suggestions", page)
    except Exception:  # noqa: BLE001
        logger.exception("suggestions mirror upsert 실패 (write-through, 응답은 정상)")
    return _from_notion_page(page)


@router.patch("/{page_id}", response_model=SuggestionItem)
async def update_suggestion(
    page_id: str,
    body: SuggestionUpdate,
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> SuggestionItem:
    # 기존 페이지 fetch (권한 체크에 작성자 필요)
    try:
        page = await notion.get_page(page_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc

    is_admin_or_lead = user.role in {"admin", "team_lead"}
    # PR-CP: 작성자 read는 multi_select 우선 (운영) + rich_text fallback
    _author_props = page.get("properties", {})
    _author_list = P.multi_select_names(_author_props, "작성자")
    page_author = _author_list[0] if _author_list else P.rich_text(_author_props, "작성자")
    is_owner = (user.name or user.username) == page_author

    update_props: dict[str, Any] = {}

    # 제목/내용/구분 — 작성자 본인 또는 admin/team_lead 만 (PR-CO)
    if body.title is not None:
        if not (is_owner or is_admin_or_lead):
            raise HTTPException(
                status_code=403, detail="본인이 작성한 글만 수정 가능"
            )
        title_prop = await _get_title_prop_name(notion)
        update_props[title_prop] = {
            "title": [{"text": {"content": body.title.strip()}}]
        }
    if body.content is not None:
        if not (is_owner or is_admin_or_lead):
            raise HTTPException(
                status_code=403, detail="본인이 작성한 글만 수정 가능"
            )
        update_props["방안"] = {"rich_text": [{"text": {"content": body.content}}]}
    if body.categories is not None:
        if not (is_owner or is_admin_or_lead):
            raise HTTPException(
                status_code=403, detail="본인이 작성한 글만 수정 가능"
            )
        update_props["구분"] = {
            "multi_select": [{"name": c} for c in body.categories if c.strip()]
        }

    # 진행상황 / 조치내용 — admin/team_lead 전용
    if body.status is not None:
        if not is_admin_or_lead:
            raise HTTPException(
                status_code=403, detail="진행상황 변경은 관리자/팀장만 가능"
            )
        if body.status not in _VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"잘못된 상태: {body.status}")
        update_props["진행상황"] = {"status": {"name": body.status}}
    if body.resolution is not None:
        if not is_admin_or_lead:
            raise HTTPException(
                status_code=403, detail="조치내용 작성은 관리자/팀장만 가능"
            )
        update_props["조치내용"] = {
            "rich_text": [{"text": {"content": body.resolution}}]
        }

    if not update_props:
        raise HTTPException(status_code=400, detail="갱신할 필드가 없습니다")

    updated = await notion.update_page(page_id, update_props)
    # PR-EX/3: write-through
    try:
        get_sync().upsert_page("suggestions", updated)
    except Exception:  # noqa: BLE001
        logger.exception("suggestions mirror upsert 실패 (write-through, 응답은 정상)")
    return _from_notion_page(updated)


@router.delete("/{page_id}")
async def delete_suggestion(
    page_id: str,
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> dict[str, str]:
    """건의사항 archive — 작성자 본인 또는 admin/team_lead 만."""
    import asyncio

    try:
        page = await notion.get_page(page_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc

    # PR-CP: 작성자 read는 multi_select 우선 (운영) + rich_text fallback
    _author_props = page.get("properties", {})
    _author_list = P.multi_select_names(_author_props, "작성자")
    page_author = _author_list[0] if _author_list else P.rich_text(_author_props, "작성자")
    is_owner = (user.name or user.username) == page_author
    is_admin_or_lead = user.role in {"admin", "team_lead"}
    if not (is_owner or is_admin_or_lead):
        raise HTTPException(
            status_code=403, detail="본인 글만 삭제 가능 (관리자/팀장은 모두 가능)"
        )

    await asyncio.to_thread(notion._client.pages.update, page_id=page_id, archived=True)
    notion.clear_cache()
    # PR-EX/3: write-through — mirror에 archived=True 즉시 반영
    try:
        get_sync().archive_page("suggestions", page_id)
    except Exception:  # noqa: BLE001
        logger.exception("suggestions mirror archive 실패 (write-through, 응답은 정상)")
    return {"status": "archived"}
