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

from app.exceptions import NotFoundError
from app.models.auth import User
from app.security import get_current_user
from app.services import notion_props as P
from app.services.notion import NotionService, get_notion
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


def _from_notion_page(page: dict[str, Any]) -> SuggestionItem:
    """PR-CO: 운영 노션 schema 매핑 — title="내용"(title), content="방안"(rich_text),
    categories="구분"(multi_select), status="진행상황"(status type), resolution="조치내용".
    """
    props = page.get("properties", {})
    # title 컬럼명은 dynamic이지만 read는 "type=title"인 첫 컬럼만 잡으면 됨 (helper 동일).
    # 운영은 title 컬럼명이 "내용"이라 기존 P.title("제목")이 빈 string 반환 → 502는 write에서만.
    # read는 안전하게 dynamic lookup 후 한 번 찾아두면 OK이지만 sync 함수라 일단 운영 컬럼명 직접 매핑.
    title_text = P.title(props, "내용") or P.title(props, "제목") or P.title(props, "Name")
    return SuggestionItem(
        id=page.get("id", ""),
        title=title_text,
        content=P.rich_text(props, "방안"),
        author=P.rich_text(props, "작성자"),
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
async def list_suggestions(
    _user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> SuggestionListResponse:
    """모든 건의사항 — 최신 작성순."""
    pages = await notion.query_all(
        _db_id(),
        sorts=[{"timestamp": "created_time", "direction": "descending"}],
    )
    items = [_from_notion_page(p) for p in pages]
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
    props: dict[str, Any] = {
        title_prop: {"title": [{"text": {"content": body.title.strip()}}]},
        "방안": {"rich_text": [{"text": {"content": body.content}}]},
        "작성자": {
            "rich_text": [{"text": {"content": user.name or user.username}}]
        },
        "진행상황": {"status": {"name": "접수"}},
    }
    if body.categories:
        props["구분"] = {
            "multi_select": [{"name": c} for c in body.categories if c.strip()]
        }
    page = await notion.create_page(_db_id(), props)
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
    page_author = P.rich_text(page.get("properties", {}), "작성자")
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

    page_author = P.rich_text(page.get("properties", {}), "작성자")
    is_owner = (user.name or user.username) == page_author
    is_admin_or_lead = user.role in {"admin", "team_lead"}
    if not (is_owner or is_admin_or_lead):
        raise HTTPException(
            status_code=403, detail="본인 글만 삭제 가능 (관리자/팀장은 모두 가능)"
        )

    await asyncio.to_thread(notion._client.pages.update, page_id=page_id, archived=True)
    notion.clear_cache()
    return {"status": "archived"}
