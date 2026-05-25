"""PR-FO Phase 1.3.1 회귀 테스트 — Transactional Outbox 인프라.

호출자(write endpoint enqueue)는 다음 PR에서 활성화. 본 테스트는 helper /
worker / monitoring 단위 동작 검증.
"""
from __future__ import annotations

import pytest

from app.models.notion_outbox import (
    OP_CREATE,
    OP_DELETE,
    OP_UPDATE,
    STATUS_DEAD,
    STATUS_PENDING,
    STATUS_RETRY,
    STATUS_SENT,
    is_active_status,
)
from app.scripts.outbox_drain import _next_attempt_delay


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
