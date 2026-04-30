"""NAVER WORKS Calendar 동기화 매핑 — 노션 task ↔ WORKS event.

한 노션 task는 N개의 calendar event로 매핑될 수 있음 (담당자 N명 + 공유 캘린더 1개).
중복 생성 방지 + task 수정/삭제 시 모든 event 갱신/삭제하기 위해 매핑 보관.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CalendarEventLink(Base):
    """노션 task를 어느 NAVER WORKS 캘린더에 어느 event로 mapping했는지."""

    __tablename__ = "calendar_event_links"
    __table_args__ = (
        UniqueConstraint(
            "notion_task_id",
            "target_user_id",
            "calendar_id",
            name="uq_cal_link_task_user_cal",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 노션 task page id (이 앱의 source of truth)
    notion_task_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # 그 캘린더의 owner인 NAVER WORKS user id (개인 캘린더는 본인, 공유 캘린더는 admin)
    target_user_id: Mapped[str] = mapped_column(String, nullable=False)
    # '' 면 기본 캘린더(/calendar/events). 값 있으면 특정 캘린더(/calendars/{id}/events)
    calendar_id: Mapped[str] = mapped_column(String, nullable=False, default="")
    # NAVER WORKS event id (CREATE 응답의 eventComponents[0].eventId)
    event_id: Mapped[str] = mapped_column(String, nullable=False)
    # 공유 캘린더에 만든 event면 True (UI 식별용)
    is_shared: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )
