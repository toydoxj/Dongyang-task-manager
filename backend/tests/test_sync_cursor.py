"""incremental sync cursor + overlap 회귀 방지.

원래 bug: `_record_success`가 since를 sync 종료 시각(`_utcnow()`)으로 박았다.
노션 query는 strict `last_edited_time > since` filter라, sync가 T_start ~ T_end
사이 진행되는 동안 새로 추가된 페이지(last_edited_time < T_end)가 다음 incremental
의 `> T_end` filter에서 누락되어 영구 안 잡혔다.

fix: (1) `sync_kind` 시작에 `start_time` capture → since로 박기, (2) query는
`since - 60s` lookback overlap. 이 테스트는 그 동작을 검증한다.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from app.services.sync import _INCREMENTAL_OVERLAP, NotionSyncService


class _FakeSession:
    """`with session_factory() as db:` 흐름을 받기 위한 최소 stub."""

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, *_: Any) -> None:
        pass

    def commit(self) -> None:
        pass


def _build_service(prev_since: datetime | None) -> tuple[NotionSyncService, dict]:
    """sync_kind 의존성을 모두 mock한 NotionSyncService 인스턴스 생성.

    sync_kind는 streaming(iter_query_pages) 사용 — async generator로 mock.
    """
    captured: dict[str, Any] = {}
    notion = MagicMock()

    async def _iter_capture(
        db_id: str,
        *,
        filter: dict[str, Any] | None = None,
        sorts: list[dict[str, Any]] | None = None,
    ):
        captured["filter"] = filter
        captured["sorts"] = sorts
        # 비어있는 결과 — async generator라 yield 없이 종료
        return
        yield  # 도달 안 함, async generator 표시용

    notion.iter_query_pages = _iter_capture

    svc = NotionSyncService.__new__(NotionSyncService)
    svc.notion = notion
    svc.session_factory = lambda: _FakeSession()
    svc.settings = MagicMock()

    svc._db_id_for = MagicMock(return_value="db-id")  # type: ignore[method-assign]
    svc._get_since = MagicMock(return_value=prev_since)  # type: ignore[method-assign]
    svc._record_success = MagicMock(  # type: ignore[method-assign]
        side_effect=lambda *a, **kw: captured.update(record_kw=kw)
    )
    return svc, captured


async def test_incremental_filter_uses_since_minus_overlap() -> None:
    """직전 since에서 60초를 뺀 시각으로 노션 query filter가 생성되어야 한다."""
    prev_since = datetime(2026, 4, 30, 9, 0, 0, tzinfo=timezone.utc)
    svc, captured = _build_service(prev_since)

    await svc.sync_kind("master", full=False)

    expected_after = (prev_since - _INCREMENTAL_OVERLAP).isoformat()
    assert captured["filter"] == {
        "timestamp": "last_edited_time",
        "last_edited_time": {"after": expected_after},
    }


async def test_incremental_records_start_time_not_end_time() -> None:
    """_record_success에 넘기는 next_since는 sync 시작 시각(이전~이후 사이)이어야 한다.

    이게 바로 회귀 방지 핵심: 종료 시각으로 박으면 이번 sync 진행 중 추가된 페이지가
    다음 sync에서 누락된다.
    """
    prev_since = datetime(2026, 4, 30, 9, 0, 0, tzinfo=timezone.utc)
    svc, captured = _build_service(prev_since)

    before = datetime.now(timezone.utc)
    await svc.sync_kind("master", full=False)
    after = datetime.now(timezone.utc)

    record_kw = captured["record_kw"]
    next_since = record_kw["next_since"]
    assert next_since is not None
    # 시작 시각은 sync_kind 호출 전후 사이
    assert before <= next_since <= after
    # 종료 시각이 아닌 시작 시각으로 박혔는지 — 호출 직전 timestamp와 차이가
    # 작아야 함 (query_all은 즉시 빈 list 반환이므로 거의 0초)
    assert (next_since - before).total_seconds() < 1.0


async def test_full_sync_skips_filter_but_still_records_start_time() -> None:
    """full=True면 filter 없이 모든 페이지를 가져오지만, since 갱신은 동일하게
    시작 시각으로 박혀야 한다 (다음 incremental의 cursor 기준점)."""
    svc, captured = _build_service(prev_since=None)

    await svc.sync_kind("master", full=True)

    # full sync는 filter 미사용 (None)
    assert captured["filter"] is None

    # 그래도 next_since는 전달됨
    record_kw = captured["record_kw"]
    assert record_kw["next_since"] is not None
    assert record_kw["full"] is True


async def test_no_prev_since_first_run_no_filter() -> None:
    """sync state가 비어 있는 첫 run은 filter 없이 전체 query — overlap 적용 X."""
    svc, captured = _build_service(prev_since=None)

    await svc.sync_kind("master", full=False)

    # 첫 incremental은 since=None → filter 없음 (전체 query)
    assert captured["filter"] is None
    # next_since는 시작 시각으로 갱신됨
    assert captured["record_kw"]["next_since"] is not None
