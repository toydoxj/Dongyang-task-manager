"""Transactional Outbox 모델 — PR-FO Phase 1.3.1.

write endpoint이 (mirror update + outbox enqueue)를 같은 transaction에서 commit해
사용자 응답 path에서 노션 호출 제거. 호출자 변경은 별도 PR (1.3.2 이후).

Codex 자문 schema:
- aggregate_type/aggregate_id: 도메인별 식별 ('seal_requests', 'tasks', ...)
- notion_page_id: create op만 NULL (push 성공 시 채움)
- op: 'create' | 'update' | 'delete'
- payload: 노션 props dict (또는 archive=True)
- status: 'pending' | 'processing' | 'retry' | 'sent' | 'dead'
- dedupe_key UNIQUE: 같은 entity 같은 version 중복 enqueue 회피
- next_attempt_at: exponential backoff 다음 시도 시간
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class NotionOutbox(Base):
    __tablename__ = "notion_outbox"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    aggregate_type: Mapped[str] = mapped_column(String, nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String, nullable=False)
    # create op만 NULL. drain worker가 push 성공 시 채움.
    notion_page_id: Mapped[str | None] = mapped_column(String, nullable=True)
    op: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending"
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lock_owner: Mapped[str | None] = mapped_column(String, nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_notion_outbox_dedupe_key"),
        Index("ix_notion_outbox_status_next", "status", "next_attempt_at"),
        Index("ix_notion_outbox_aggregate", "aggregate_type", "aggregate_id"),
    )


# 상수 정의 (helper / worker / monitoring에서 import)
STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_RETRY = "retry"
STATUS_SENT = "sent"
STATUS_DEAD = "dead"
_ACTIVE_STATUSES = (STATUS_PENDING, STATUS_PROCESSING, STATUS_RETRY)

OP_CREATE = "create"
OP_UPDATE = "update"
OP_DELETE = "delete"


def is_active_status(status: str) -> bool:
    """drain worker가 pickup 대상으로 보는 status."""
    return status in _ACTIVE_STATUSES
