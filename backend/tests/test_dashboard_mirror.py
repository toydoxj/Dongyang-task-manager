"""PR-FM Phase 1.2 회귀 테스트 — /dashboard overdue_seals mirror 전환.

INCIDENT.md 2026-05-22 후속. PR-EW의 운영 6.4초 병목(notion query_all) 제거,
mirror_seal_requests SELECT로 동등 결과.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from app.routers.dashboard import (
    _PENDING_SEAL_STATUSES,
    _collect_overdue_seals,
)


def _row(*, title: str, properties: dict | None) -> tuple:
    """SELECT title, properties 결과 row 시뮬레이션."""
    return (title, properties)


def _props_with_due(due_iso: str, *, title: str = "doc") -> dict:
    """노션 raw properties 형식 (mirror.properties에 저장되는 형식)."""
    return {
        "제목": {"type": "title", "title": [{"plain_text": title}]},
        "제출예정일": {"type": "date", "date": {"start": due_iso}},
    }


def test_collect_overdue_seals_uses_mirror_only() -> None:
    """notion 호출 없이 db.execute 결과만으로 동작."""
    today = date(2026, 5, 25)
    db = MagicMock()
    # 3 rows: 2개 overdue + 1개 미래
    db.execute.return_value.all.return_value = [
        _row(title="과거1", properties=_props_with_due("2026-05-20", title="과거1")),
        _row(title="미래", properties=_props_with_due("2026-06-01", title="미래")),
        _row(title="과거2", properties=_props_with_due("2026-05-22", title="과거2")),
    ]
    result = _collect_overdue_seals(db, today)
    # 가장 오래된 것이 preview ("과거1" → 2026-05-20)
    assert result.count == 2
    assert result.preview == "과거1"
    # notion 의존 없음 — execute 1회만 호출
    assert db.execute.call_count == 1


def test_collect_overdue_seals_skips_null_properties() -> None:
    """properties=NULL 옛 row(backfill 전)는 안전 skip — 'KeyError' 없이 통과."""
    today = date(2026, 5, 25)
    db = MagicMock()
    db.execute.return_value.all.return_value = [
        _row(title="legacy", properties=None),
        _row(title="legacy2", properties={}),
        _row(title="과거", properties=_props_with_due("2026-05-20", title="과거")),
    ]
    result = _collect_overdue_seals(db, today)
    assert result.count == 1
    assert result.preview == "과거"


def test_collect_overdue_seals_title_fallback() -> None:
    """mirror.title이 있으면 우선 사용 (properties title보다 mirror 컬럼이 정규화)."""
    today = date(2026, 5, 25)
    db = MagicMock()
    db.execute.return_value.all.return_value = [
        _row(
            title="mirror-title",
            properties=_props_with_due("2026-05-20", title="props-title"),
        ),
    ]
    result = _collect_overdue_seals(db, today)
    assert result.preview == "mirror-title"


def test_pending_statuses_constant() -> None:
    """status filter 상수 — sync.py SL.normalize_status와 일치해야 함."""
    assert "1차검토 중" in _PENDING_SEAL_STATUSES
    assert "2차검토 중" in _PENDING_SEAL_STATUSES
    assert "승인" not in _PENDING_SEAL_STATUSES
