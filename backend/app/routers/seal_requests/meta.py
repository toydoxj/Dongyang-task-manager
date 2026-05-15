"""날인요청 메타 endpoint — 다음 문서번호 미리보기, 본인 처리 대기 건수.

PR-CG (Phase 4-J 5단계): seal_requests/__init__.py 분할 시작.
가장 작은 read-only endpoint 2개를 sub-router로 분리.

상위 router(`prefix="/seal-requests"`)가 prefix 상속.
"""
from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.models.auth import User
from app.security import get_current_user
from app.services import seal_logic as SL
from app.services.notion import NotionService, get_notion
from app.settings import get_settings

logger = logging.getLogger("api.seal_requests.meta")
router = APIRouter()

# PR-CK: pending-count TTL cache. role별로 key 분리. multi-worker별 in-memory.
# Sidebar의 60초 polling이 5분 TTL 동안 cache hit → 노션 호출 5분에 1회.
_PENDING_CACHE_TTL_S = 300.0  # 5분
_pending_count_cache: dict[str, tuple[float, int]] = {}


# ── helper (중복 정의 — __init__.py와 동일. 다른 endpoint도 사용해 추출 못 함) ──


def _db_id() -> str:
    db_id = get_settings().notion_db_seal_requests
    if not db_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="NOTION_DB_SEAL_REQUESTS 미설정",
        )
    return db_id


# ── models ──


class NextDocNumberResponse(BaseModel):
    """다음 발급될 문서번호 (구조검토서만 의미). 발급은 안 함."""

    seal_type: str
    next_doc_number: str  # 빈 문자열 = 자동 발급 안 하는 type


class PendingCount(BaseModel):
    """role별 본인이 처리해야 할 건수 (사이드바 알림 배지용)."""

    count: int


# ── endpoints ──


@router.get("/next-doc-number", response_model=NextDocNumberResponse)
async def get_next_doc_number(
    seal_type: str,
    _user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> NextDocNumberResponse:
    """모달 미리보기용 — 다음 발급될 문서번호를 미리 계산.

    실제 발급은 create 시점에 다시 issue_review_doc_number 호출로. 그 사이
    다른 사용자가 한 건 발급하면 모달의 미리보기와 실제 부여 번호가 다를 수
    있음 (사용자에게 정보 제공 목적이라 허용).
    """
    seal_type = SL.normalize_type(seal_type.strip())
    if seal_type != "구조검토서":
        return NextDocNumberResponse(seal_type=seal_type, next_doc_number="")
    next_no = await SL.issue_review_doc_number(notion, _db_id())
    return NextDocNumberResponse(seal_type=seal_type, next_doc_number=next_no)


@router.get("/pending-count", response_model=PendingCount)
async def get_pending_count(
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> PendingCount:
    """본인이 처리해야 할 건수 (사이드바 알림 배지용).

    - team_lead: '1차검토 중'(또는 호환 '요청')
    - admin: '2차검토 중'(또는 호환 '팀장승인')

    PR-CK: 5분 TTL cache — Sidebar 60초 polling + 대시보드 KPI fetch 누적 부하
    완화. 노션 query_all은 페이지당 0.4s rate limit이라 cache miss 시 2~6초.
    """
    if user.role == "team_lead":
        targets = ["1차검토 중", "요청"]
    elif user.role == "admin":
        targets = ["2차검토 중", "팀장승인"]
    else:
        return PendingCount(count=0)

    # role 단위 cache (admin/team_lead만 의미). targets 키로 단순화.
    cache_key = "|".join(targets)
    now = time.monotonic()
    hit = _pending_count_cache.get(cache_key)
    if hit and (now - hit[0]) < _PENDING_CACHE_TTL_S:
        return PendingCount(count=hit[1])

    pages = await notion.query_all(
        _db_id(),
        filter={
            "or": [
                {"property": "상태", "select": {"equals": t}} for t in targets
            ]
        },
    )
    count = len(pages)
    _pending_count_cache[cache_key] = (now, count)
    return PendingCount(count=count)
