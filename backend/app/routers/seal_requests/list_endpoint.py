"""날인요청 list endpoint.

PR-CV (Phase 4-J 11단계): seal_requests/__init__.py에서 GET / 분리.
파일명은 `list.py` 대신 `list_endpoint.py` — Python builtin name 충돌 회피.

주의: weekly_report.py가 `from app.routers.seal_requests import list_seal_requests`
형태로 직접 import. __init__.py에서 re-export 유지.

상위 router(`prefix="/seal-requests"`)가 prefix 상속.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.auth import User
from app.security import get_current_user
from app.services import notion_props as P
from app.services.notion import NotionService, get_notion
from app.settings import get_settings

# PR-CV: list endpoint의 path가 빈 문자열("")이라 sub-router로 mount하면
# FastAPI의 "prefix와 path 둘 다 비면 안 됨" 검증에 걸림. router 만들지 않고
# 함수만 export → __init__.py에서 root router에 직접 add_api_route.

# module-level lazy import — __init__.py가 sub-router include 시점(파일 끝)에 fully loaded.
from app.routers.seal_requests import SealListResponse  # noqa: E402


def _db_id() -> str:
    """meta.py / delete.py와 동일 helper — 중복 정의 (외과적, 2줄)."""
    db_id = get_settings().notion_db_seal_requests
    if not db_id:
        raise HTTPException(status_code=500, detail="NOTION_DB_SEAL_REQUESTS 미설정")
    return db_id


async def list_seal_requests(
    project_id: str | None = None,
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
    db: Session = Depends(get_db),
) -> SealListResponse:
    """날인요청 목록.

    docs/request.md: 일반직원은 날인요청 페이지 접근 불가. 단 프로젝트 상세에서
    `project_id` 필터로 자신의 프로젝트 진행 상황은 확인 가능 — 이 경우는 허용.
    """
    from app.routers.seal_requests import (
        _filter_accessible,
        _from_notion_page,
        _sort_items_by_role,
    )

    if user.role not in {"admin", "team_lead"} and not project_id:
        raise HTTPException(
            status_code=403,
            detail="일반직원은 날인요청 페이지를 직접 조회할 수 없습니다",
        )
    pages = await notion.query_all(
        _db_id(),
        sorts=[{"timestamp": "created_time", "direction": "descending"}],
    )
    if project_id:
        pages = [
            p
            for p in pages
            if project_id in P.relation_ids(p.get("properties", {}), "프로젝트")
        ]
    pages = _filter_accessible(user, pages, db)
    items = [_from_notion_page(p) for p in pages]
    items = _sort_items_by_role(items, user.role or "member")
    return SealListResponse(items=items, count=len(items))
