"""PR-FO Phase 1.3.1 회귀 테스트 — Transactional Outbox 인프라.

호출자(write endpoint enqueue)는 다음 PR에서 활성화. 본 테스트는 helper /
worker / monitoring 단위 동작 검증.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.models.notion_outbox import (
    OP_CREATE,
    OP_DELETE,
    OP_UPDATE,
    STATUS_DEAD,
    STATUS_PENDING,
    STATUS_PROCESSING,
    STATUS_RETRY,
    STATUS_SENT,
    is_active_status,
)
from app.scripts.outbox_drain import (
    _is_archived_target_error,
    _mark_stale_processing_rows_retry,
    _next_attempt_delay,
    _should_skip_archived_target,
)


def test_active_statuses() -> None:
    """drain worker pickup 대상 status — pending / processing / retry."""
    assert is_active_status(STATUS_PENDING) is True
    assert is_active_status(STATUS_RETRY) is True
    assert is_active_status(STATUS_SENT) is False
    assert is_active_status(STATUS_DEAD) is False


def test_exponential_backoff_schedule() -> None:
    """retry delay — 30s, 60s, 120s, ..., cap 3600s (1시간)."""
    assert _next_attempt_delay(1) == 30
    assert _next_attempt_delay(2) == 60
    assert _next_attempt_delay(3) == 120
    assert _next_attempt_delay(4) == 240
    assert _next_attempt_delay(5) == 480
    assert _next_attempt_delay(6) == 960
    assert _next_attempt_delay(7) == 1920
    # cap 3600s
    assert _next_attempt_delay(8) == 3600
    assert _next_attempt_delay(20) == 3600


def test_stale_processing_rows_are_reset_to_retry() -> None:
    """stale processing row는 attempts 증가 없이 즉시 retry 가능 상태로 회수."""
    now = datetime(2026, 5, 27, 14, 50, tzinfo=timezone.utc)
    row = SimpleNamespace(
        status=STATUS_PROCESSING,
        locked_at=datetime(2026, 5, 25, 8, 2, tzinfo=timezone.utc),
        lock_owner="old-worker",
        next_attempt_at=datetime(2026, 5, 25, 8, 1, tzinfo=timezone.utc),
        last_error="",
    )

    assert _mark_stale_processing_rows_retry([row], now) == 1
    assert row.status == STATUS_RETRY
    assert row.locked_at is None
    assert row.lock_owner is None
    assert row.next_attempt_at == now
    assert row.last_error == "stale processing lock recovered"


def test_archived_target_error_detection() -> None:
    """Notion archived page/block 수정 거부 오류를 별도 분류."""
    err = Exception("노션 API 호출 실패: Can't edit block that is archived.")
    assert _is_archived_target_error(err) is True
    assert _is_archived_target_error(Exception("temporary timeout")) is False


def test_archived_target_can_be_skipped_when_mirror_is_archived() -> None:
    """mirror가 archived이면 archived target 오류는 목표 상태 달성으로 간주."""
    from unittest.mock import MagicMock

    db = MagicMock()
    db.get.return_value = SimpleNamespace(archived=True)
    row = SimpleNamespace(
        op=OP_UPDATE,
        aggregate_type="seal_requests",
        aggregate_id="page-1",
        notion_page_id="page-1",
    )
    err = Exception("Can't edit block that is archived. You must unarchive first.")

    assert _should_skip_archived_target(db, row, err) is True


def test_op_constants_match_valid_set() -> None:
    """helper의 _VALID_OPS와 model 상수 일치 검증."""
    from app.services.notion_outbox import _VALID_OPS

    assert OP_CREATE in _VALID_OPS
    assert OP_UPDATE in _VALID_OPS
    assert OP_DELETE in _VALID_OPS


def test_enqueue_rejects_invalid_op() -> None:
    """잘못된 op는 ValueError."""
    from unittest.mock import MagicMock

    from app.services.notion_outbox import enqueue

    db = MagicMock()
    with pytest.raises(ValueError, match="invalid op"):
        enqueue(db, aggregate_type="seal_requests", aggregate_id="p1",
                op="patch", payload={})


def test_enqueue_update_requires_notion_page_id() -> None:
    """update/delete op는 notion_page_id 필수."""
    from unittest.mock import MagicMock

    from app.services.notion_outbox import enqueue

    db = MagicMock()
    with pytest.raises(ValueError, match="requires notion_page_id"):
        enqueue(db, aggregate_type="seal_requests", aggregate_id="p1",
                op="update", payload={"prop": "value"})
    with pytest.raises(ValueError, match="requires notion_page_id"):
        enqueue(db, aggregate_type="seal_requests", aggregate_id="p1",
                op="delete", payload={})


def test_enqueue_create_allows_null_notion_page_id() -> None:
    """create op는 notion_page_id=None 허용 (push 후 채워짐)."""
    from unittest.mock import MagicMock

    from app.services.notion_outbox import enqueue

    db = MagicMock()
    db.execute.return_value.first.return_value = None  # dedupe 검사 no match
    row = enqueue(
        db, aggregate_type="seal_requests", aggregate_id="new-id",
        op="create", payload={"title": "test"},
    )
    # db.add 호출 확인 (실제 insert는 mock이라 None 반환 안 됨 — Mock의 자동 응답)
    assert db.add.called


def test_enqueue_dedupe_skip() -> None:
    """같은 dedupe_key가 active이면 skip → None 반환."""
    from unittest.mock import MagicMock

    from app.services.notion_outbox import enqueue

    db = MagicMock()
    # dedupe 검사에 기존 active row 발견
    existing = MagicMock(id=42, status=STATUS_PENDING)
    db.execute.return_value.first.return_value = existing
    result = enqueue(
        db, aggregate_type="seal_requests", aggregate_id="p1",
        op="update", payload={"x": 1}, notion_page_id="p1",
        dedupe_key="seal_requests:p1:v1",
    )
    assert result is None  # dedupe로 skip
    assert not db.add.called
