"""노션 → Postgres 미러 ORM.

각 모델은 노션 페이지를 1:1로 미러링. 자주 필터/정렬하는 컬럼만 정규화하고
나머지는 properties JSONB에 보관 (도메인 변경에 유연).
PostgreSQL 전용 (JSONB / ARRAY). 로컬 dev도 Supabase 직결 권장.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MirrorProject(Base):
    __tablename__ = "mirror_projects"

    page_id: Mapped[str] = mapped_column(String, primary_key=True)
    code: Mapped[str] = mapped_column(String, default="", index=True)
    master_code: Mapped[str] = mapped_column(String, default="")
    master_project_id: Mapped[str] = mapped_column(String, default="", index=True)
    name: Mapped[str] = mapped_column(String, default="")
    stage: Mapped[str] = mapped_column(String, default="", index=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    assignees: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    teams: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    client_relation_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    url: Mapped[str] = mapped_column(String, default="")
    last_edited_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class MirrorTask(Base):
    __tablename__ = "mirror_tasks"

    page_id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, default="")
    code: Mapped[str] = mapped_column(String, default="")
    project_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    status: Mapped[str] = mapped_column(String, default="", index=True)
    priority: Mapped[str] = mapped_column(String, default="")
    difficulty: Mapped[str] = mapped_column(String, default="")
    progress: Mapped[float | None] = mapped_column(Float, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    actual_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    assignees: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    teams: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    url: Mapped[str] = mapped_column(String, default="")
    created_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_edited_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class MirrorClient(Base):
    __tablename__ = "mirror_clients"

    page_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, default="", index=True)
    category: Mapped[str] = mapped_column(String, default="")
    properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    last_edited_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class MirrorMaster(Base):
    __tablename__ = "mirror_master_projects"

    page_id: Mapped[str] = mapped_column(String, primary_key=True)
    code: Mapped[str] = mapped_column(String, default="", index=True)
    name: Mapped[str] = mapped_column(String, default="")
    sub_project_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    url: Mapped[str] = mapped_column(String, default="")
    last_edited_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class MirrorCashflow(Base):
    __tablename__ = "mirror_cashflow"

    page_id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String, default="income", index=True)  # income | expense
    project_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    amount: Mapped[float] = mapped_column(Float, default=0)
    category: Mapped[str] = mapped_column(String, default="")
    note: Mapped[str] = mapped_column(Text, default="")
    properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    last_edited_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class MirrorBlock(Base):
    """페이지 본문 블록 (특히 마스터 프로젝트의 image block)."""

    __tablename__ = "mirror_blocks"

    block_id: Mapped[str] = mapped_column(String, primary_key=True)
    parent_page_id: Mapped[str] = mapped_column(String, default="", index=True)
    type: Mapped[str] = mapped_column(String, default="", index=True)
    content: Mapped[dict] = mapped_column(JSONB, default=dict)
    position: Mapped[int] = mapped_column(default=0)  # 페이지 내 순서
    last_edited_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class NotionSyncState(Base):
    """sync 진행 상태 — 다음 incremental sync의 since 기준."""

    __tablename__ = "notion_sync_state"

    db_kind: Mapped[str] = mapped_column(String, primary_key=True)  # projects|tasks|clients|...
    last_incremental_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_full_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str] = mapped_column(Text, default="")
    last_run_count: Mapped[int] = mapped_column(default=0)
