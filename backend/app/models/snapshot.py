"""주간 스냅샷 ORM (PR-W weekly_snapshot).

매주 일요일 23:59 KST에 모든 진행 중 프로젝트의 진행률·단계·담당자를 박제.
주간 보고서의 Δ(진행률 변화) 표시를 위한 인프라 — 4주 누적 후 활용.

`week_start`는 해당 주차의 월요일 (해당 주에 속한 스냅샷이 누구의 것인지 명확).
일요일 23:59에 찍지만 다음 주의 월요일을 기준으로 저장 — 다음 보고서가 곧바로 참조.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProjectSnapshot(Base):
    __tablename__ = "project_snapshots"

    # composite PK는 alembic 다루기 까다로우므로 surrogate id 사용
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    week_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)  # 월요일

    # 박제 시점 값
    code: Mapped[str] = mapped_column(String, default="")
    name: Mapped[str] = mapped_column(String, default="")
    stage: Mapped[str] = mapped_column(String, default="")
    progress: Mapped[float] = mapped_column(Float, default=0.0)  # 0~1
    assignees: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    teams: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)  # 향후 확장용 (마감일, 진행률 산출 source 등)

    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        UniqueConstraint("project_id", "week_start", name="uq_project_snapshots_project_week"),
    )
