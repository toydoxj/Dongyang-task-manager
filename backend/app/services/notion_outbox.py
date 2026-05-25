"""Transactional Outbox helper — PR-FO Phase 1.3.1.

write endpoint이 (mirror update + outbox enqueue)를 같은 transaction에서 commit해
사용자 응답 path에서 노션 호출 제거.

호출 패턴 (다음 PR에서 활성화):
```python
with db.begin():  # 또는 FastAPI Depends(get_db) yield + db.commit()
    db.execute(update(MirrorSealRequest).where(...).values(...))
    enqueue(db, aggregate_type='seal_requests', aggregate_id=page_id,
            op='update', payload=props, notion_page_id=page_id,
            dedupe_key=f'seal_requests:{page_id}:v{version}')
# 같은 transaction commit
# 사용자에게 즉시 응답
```
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.notion_outbox import (
    OP_CREATE,
    OP_DELETE,
    OP_UPDATE,
    STATUS_PENDING,
    NotionOutbox,
    _ACTIVE_STATUSES,
)

logger = logging.getLogger("notion_outbox")

_VALID_OPS = {OP_CREATE, OP_UPDATE, OP_DELETE}


def enqueue(
    db: Session,
    *,
    aggregate_type: str,
    aggregate_id: str,
    op: str,
    payload: dict,
    notion_page_id: str | None = None,
    dedupe_key: str | None = None,
) -> NotionOutbox | None:
    """Outbox에 노션 push 작업을 큐잉. 호출자의 db transaction 안에서 호출.

    같은 dedupe_key가 이미 pending/retry 상태이면 skip (idempotent re-enqueue).
    그 외에는 신규 row insert. db.commit()은 호출자 책임 (mirror update와 원자성).

    Args:
        aggregate_type: 'seal_requests', 'tasks', 'projects', ... 도메인 구분
        aggregate_id: entity의 stable identifier (보통 mirror page_id)
        op: 'create' | 'update' | 'delete'
        payload: 노션 props dict (delete의 경우 빈 dict 또는 archive flag)
        notion_page_id: update/delete는 필수. create는 None (push 후 채워짐)
        dedupe_key: 중복 enqueue 방지 키. 예: f'{type}:{id}:v{ver}'

    Returns:
        새로 insert된 row 또는 dedupe로 skip 시 None.
    """
    if op not in _VALID_OPS:
        raise ValueError(f"invalid op: {op}. Expected one of {_VALID_OPS}")
    if op in (OP_UPDATE, OP_DELETE) and not notion_page_id:
        raise ValueError(f"{op} requires notion_page_id")

    # dedupe: 같은 dedupe_key가 이미 active(pending/processing/retry)면 skip
    if dedupe_key:
        existing = db.execute(
            select(NotionOutbox.id, NotionOutbox.status).where(
                NotionOutbox.dedupe_key == dedupe_key,
                NotionOutbox.status.in_(_ACTIVE_STATUSES),
            )
        ).first()
        if existing is not None:
            logger.info(
                "outbox dedupe skip — dedupe_key=%s status=%s existing_id=%d",
                dedupe_key, existing.status, existing.id,
            )
            return None

    row = NotionOutbox(
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        notion_page_id=notion_page_id,
        op=op,
        payload=payload or {},
        status=STATUS_PENDING,
        dedupe_key=dedupe_key,
    )
    db.add(row)
    db.flush()  # id 채우기 (commit은 호출자)
    return row


def has_active(db: Session, aggregate_type: str, aggregate_id: str) -> bool:
    """해당 entity에 active outbox row가 있는지.

    reconcile 정책(별도 PR): migrated 도메인에서 active outbox 있는 entity는
    노션 → mirror overwrite를 건너뛴다 (사용자 미반영 변경 손실 방지).
    """
    cnt = db.execute(
        select(func.count(NotionOutbox.id)).where(
            NotionOutbox.aggregate_type == aggregate_type,
            NotionOutbox.aggregate_id == aggregate_id,
            NotionOutbox.status.in_(_ACTIVE_STATUSES),
        )
    ).scalar_one()
    return int(cnt) > 0


def status_summary(db: Session) -> list[dict]:
    """admin 모니터링용 — status별 count + 가장 오래된 row created_at.

    Returns:
        [{"status": "pending", "count": 3, "oldest_created_at": "2026-05-25T..."}]
    """
    rows = db.execute(
        select(
            NotionOutbox.status,
            func.count(NotionOutbox.id),
            func.min(NotionOutbox.created_at),
        ).group_by(NotionOutbox.status)
    ).all()
    return [
        {
            "status": s,
            "count": int(c),
            "oldest_created_at": (
                o.astimezone(timezone.utc).isoformat() if o else None
            ),
        }
        for s, c, o in rows
    ]
