"""날인요청 list endpoint.

PR-CV (Phase 4-J 11단계): seal_requests/__init__.py에서 GET / 분리.
파일명은 `list.py` 대신 `list_endpoint.py` — Python builtin name 충돌 회피.

PR-FL Phase 1.1: 사용자 facing 노션 호출 제거 → mirror SELECT 전환. 응답 시간
2~3초 → ~50ms. INCIDENT.md 2026-05-22 만성 hang 근본 해결.

주의: weekly_report.py가 `from app.routers.seal_requests import list_seal_requests`
형태로 직접 import. __init__.py에서 re-export 유지.

상위 router(`prefix="/seal-requests"`)가 prefix 상속.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import mirror as M
from app.models.auth import User
from app.security import get_current_user
from app.services.notion import NotionService, get_notion

# PR-CV: list endpoint의 path가 빈 문자열("")이라 sub-router로 mount하면
# FastAPI의 "prefix와 path 둘 다 비면 안 됨" 검증에 걸림. router 만들지 않고
# 함수만 export → __init__.py에서 root router에 직접 add_api_route.

# module-level lazy import — __init__.py가 sub-router include 시점(파일 끝)에 fully loaded.
from app.routers.seal_requests import SealListResponse  # noqa: E402


def _mirror_row_to_notion_page(row: M.MirrorSealRequest) -> dict:
    """mirror row → _from_notion_page가 기대하는 page-like dict.

    PR-FL: sync.py가 노션 page.properties 통째 저장하므로 page 재구성은 fields만
    재조립. _from_notion_page는 properties dict의 노션 raw 형식(date_range/relation/...)을
    그대로 읽어 SealRequestItem 응답 생성.
    """
    return {
        "id": row.page_id,
        "properties": row.properties or {},
        "created_time": row.created_time.isoformat() if row.created_time else None,
        "last_edited_time": (
            row.last_edited_time.isoformat() if row.last_edited_time else None
        ),
    }


async def list_seal_requests(
    project_id: str | None = None,
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),  # signature 유지 (호출자 forward)
    db: Session = Depends(get_db),
) -> SealListResponse:
    """날인요청 목록 — mirror SELECT 기반 (PR-FL).

    docs/request.md: 일반직원은 날인요청 페이지 접근 불가. 단 프로젝트 상세에서
    `project_id` 필터로 자신의 프로젝트 진행 상황은 확인 가능 — 이 경우는 허용.

    PR-FL: 노션 query_all(2~3초) 제거. mirror_seal_requests SELECT만 사용.
    write-through(create/update/approve/reject) + 5분 incremental sync로 lag 최소화.
    `notion` 파라미터는 signature backward-compat — 함수 본문에서 미사용. 호출자
    (weekly_report._build_seal_log)가 NotionService를 forward해도 영향 없음.
    """
    from app.routers.seal_requests import (
        _filter_accessible,
        _from_notion_page,
        _sort_items_by_role,
    )

    _ = notion  # signature 유지용 — backward compat (호출자 forward).

    if user.role not in {"admin", "team_lead"} and not project_id:
        raise HTTPException(
            status_code=403,
            detail="일반직원은 날인요청 페이지를 직접 조회할 수 없습니다",
        )

    # mirror_seal_requests SELECT — created_time DESC (옛 응답과 동일 정렬)
    stmt = select(M.MirrorSealRequest).where(
        M.MirrorSealRequest.archived.is_(False)
    )
    if project_id:
        # ARRAY contains — page_id가 project_ids에 포함된 row만.
        # 옛 노션 filter `relation.contains`와 동등.
        stmt = stmt.where(M.MirrorSealRequest.project_ids.any(project_id))  # type: ignore[attr-defined]
    stmt = stmt.order_by(M.MirrorSealRequest.created_time.desc())
    rows = db.execute(stmt).scalars().all()

    pages = [_mirror_row_to_notion_page(r) for r in rows]
    pages = _filter_accessible(user, pages, db)
    items = [_from_notion_page(p) for p in pages]
    items = _sort_items_by_role(items, user.role or "member")
    return SealListResponse(items=items, count=len(items))
