"""PR-FK Phase 0 회귀 테스트 — user_facing 노션 호출 안전망.

INCIDENT.md 2026-05-22 사고(노션 hang → backend 분 단위 cascade) 재발 방지.
Codex MCP 권장 4 시나리오.
"""
from __future__ import annotations

import asyncio
import time

import httpx
import pytest

from app.exceptions import NotionApiError
from app.services.notion import (
    NotionService,
    _RETRY_MAX_ATTEMPTS,
    _USER_MAX_ATTEMPTS,
    _USER_RETRY_DEADLINE_S,
)


@pytest.mark.asyncio
async def test_user_facing_retry_limited_to_2_attempts() -> None:
    """user_facing=True 호출은 최대 2 attempts (background 4회보다 적음)."""
    svc = NotionService("test-key")
    call_count = 0

    def fail_fn() -> None:
        nonlocal call_count
        call_count += 1
        raise httpx.TimeoutException("simulated timeout")

    start = time.monotonic()
    with pytest.raises(NotionApiError):
        await svc._call(fail_fn, user_facing=True, op_name="test")
    elapsed = time.monotonic() - start
    assert call_count == _USER_MAX_ATTEMPTS == 2
    assert elapsed < _USER_RETRY_DEADLINE_S + 2, (
        f"user-facing fail-fast 너무 느림: {elapsed:.2f}s"
    )


@pytest.mark.asyncio
async def test_background_path_keeps_4_attempts() -> None:
    """user_facing=False (default)는 기존 4 attempts 정책 유지 — 백워드 컴팩트."""
    svc = NotionService("test-key")
    call_count = 0

    def fail_fn() -> None:
        nonlocal call_count
        call_count += 1
        raise httpx.TimeoutException("simulated timeout")

    with pytest.raises(NotionApiError):
        await svc._call(fail_fn, user_facing=False, op_name="test")
    assert call_count == _RETRY_MAX_ATTEMPTS == 4


@pytest.mark.asyncio
async def test_query_all_total_budget_fail_fast_on_multi_page_delay() -> None:
    """query_all wallclock budget 초과 시 NotionApiError로 fail-fast (부분반환 없음)."""
    svc = NotionService("test-key")
    page_calls = 0

    async def slow_query(*args, **kwargs):
        nonlocal page_calls
        page_calls += 1
        await asyncio.sleep(2.0)
        # 모든 페이지가 has_more=True — budget이 발동해야 종료
        return {
            "results": [{"id": f"p{page_calls}"}],
            "has_more": True,
            "next_cursor": f"cur{page_calls}",
        }

    svc.query_database = slow_query
    start = time.monotonic()
    with pytest.raises(NotionApiError) as exc_info:
        # user_facing=True default budget=5s
        await svc.query_all("test-db", user_facing=True)
    elapsed = time.monotonic() - start
    assert "budget" in str(exc_info.value).lower()
    # 5s budget, 2s/page → 3 page (6s) 또는 그 이내에 fail-fast
    assert elapsed < 8, f"query_all budget cut 늦음: {elapsed:.2f}s"
    assert page_calls >= 2  # 최소 2 페이지 fetch 후 cut


@pytest.mark.asyncio
async def test_weekly_report_seal_log_degrade_on_notion_error() -> None:
    """`_build_seal_log`에서 NotionApiError → 빈 배열 degrade.

    list_seal_requests를 mock해 NotionApiError를 발생시키고,
    `_build_seal_log`가 empty list 반환하는지 검증.
    """
    from datetime import date
    from unittest.mock import patch

    from app.models.auth import User
    from app.routers.weekly_report import _build_seal_log

    # admin user — role swap 없이 직접 진입
    user = User(id=1, name="tester", role="admin", status="active", email="t@x")

    async def raise_notion_error(*args, **kwargs):
        raise NotionApiError("simulated notion hang")

    with patch(
        "app.routers.seal_requests.list_seal_requests",
        new=raise_notion_error,
    ):
        # db / notion mock — _build_seal_log은 mock된 list_seal_requests만 호출
        result = await _build_seal_log(
            user=user,
            notion=None,  # type: ignore[arg-type]
            db=None,  # type: ignore[arg-type]
            last_week_start=date(2026, 5, 15),
            last_week_end=date(2026, 5, 21),
        )
        assert result == []
