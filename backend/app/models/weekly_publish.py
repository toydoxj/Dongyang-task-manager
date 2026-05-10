"""주간 업무일지 발행 로그 ORM (PR-W publish).

발행 = WORKS Drive 업로드 + 전직원 알림 발송. 다음 일지 작성 시
"저번주 시작일" default를 마지막 발행된 week_end + 1일 (즉 다음 월요일)으로
자동 셋팅하기 위한 기록.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WeeklyReportPublishLog(Base):
    __tablename__ = "weekly_report_publish_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    week_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    week_end: Mapped[date] = mapped_column(Date, nullable=False)
    last_week_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_week_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, index=True
    )
    published_by: Mapped[str] = mapped_column(String, nullable=False, default="")
    file_id: Mapped[str] = mapped_column(String, nullable=False, default="")
    file_url: Mapped[str] = mapped_column(String, nullable=False, default="")
    file_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    recipient_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notify_failed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    error: Mapped[str | None] = mapped_column(String, nullable=True)
