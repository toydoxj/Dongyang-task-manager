"""사내 공지 / 교육 일정 도메인 (PR-W Phase 2.4).

주간 업무일지 1페이지의 "주요 공지사항" / "교육 일정" 섹션 source.
노션 미러가 아닌 자체 테이블 — admin이 직접 등록·수정. PLAN_WEEKLY_REPORT 권장.

게시기간(start_date~end_date)이 보고서 주차와 겹치는 row만 PDF에 표시된다.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Notice(Base):
    __tablename__ = "notices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # kind: '공지' | '교육' — 주간 업무일지의 두 섹션을 단일 테이블로 통합.
    # value 검증은 라우터 Pydantic schema에서. DB는 freeform string.
    kind: Mapped[str] = mapped_column(String, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(Text, default="")
    # 게시기간 — 주간 보고서 주차와 교집합 판정용.
    # end_date NULL이면 무기한 (start_date부터 영구 게시).
    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    author_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


# ── Pydantic ──


class NoticeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    title: str
    body: str = ""
    start_date: date
    end_date: date | None = None
    author_user_id: int | None = None
    created_at: datetime
    updated_at: datetime


class NoticeListResponse(BaseModel):
    items: list[NoticeOut]
    count: int


class NoticeCreate(BaseModel):
    kind: str  # '공지' | '교육'
    title: str
    body: str = ""
    start_date: date
    end_date: date | None = None


class NoticeUpdate(BaseModel):
    """None 필드는 변경 안 함. end_date는 빈 문자열로는 못 비우고 명시적 null 필요."""

    kind: str | None = None
    title: str | None = None
    body: str | None = None
    start_date: date | None = None
    end_date: date | None = None
