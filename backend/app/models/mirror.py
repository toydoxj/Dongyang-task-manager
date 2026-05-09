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
    category: Mapped[str] = mapped_column(String, default="", index=True)
    activity: Mapped[str] = mapped_column(String, default="", index=True)
    progress: Mapped[float | None] = mapped_column(Float, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    actual_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    assignees: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    teams: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    # 금주예정사항 (PR-W Phase 2.2) — 노션 task DB의 rich_text 컬럼 미러.
    # 주간 보고서 표 우측 컬럼 출력용. 기존 `note`(영구 비고)와 분리.
    weekly_plan_text: Mapped[str] = mapped_column(Text, default="")
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


class MirrorContractItem(Base):
    """프로젝트 계약 항목 (공동수급·추가 용역의 발주처별 분담분).

    한 프로젝트에 N개의 (발주처, 금액, 라벨) 항목이 존재할 수 있으며,
    각 수금 row는 0~1개의 contract_item에 매칭된다.
    """

    __tablename__ = "mirror_contract_items"

    page_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, default="", index=True)
    client_id: Mapped[str] = mapped_column(String, default="", index=True)
    label: Mapped[str] = mapped_column(String, default="")
    amount: Mapped[float] = mapped_column(Float, default=0)
    vat: Mapped[float] = mapped_column(Float, default=0)
    sort_order: Mapped[int] = mapped_column(default=0)
    properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    last_edited_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class MirrorSales(Base):
    """영업(Sales) 미러 — 사장이 운영하던 '견적서 작성 리스트' DB.

    수주영업(견적·입찰)과 기술지원(수주 전 자문) 두 갈래를 단일 테이블에서 관리.
    `kind` 컬럼으로 구분하고, `stage`는 두 갈래의 단계를 한 select에 합친 형태.
    `category`/`assignees`는 multi_select라 ARRAY[String]로 모델링.
    """

    __tablename__ = "mirror_sales"

    page_id: Mapped[str] = mapped_column(String, primary_key=True)
    code: Mapped[str] = mapped_column(String, default="", index=True)  # 영업코드 영{YY}-{NNN}
    name: Mapped[str] = mapped_column(String, default="")  # 견적서명 (title)
    kind: Mapped[str] = mapped_column(String, default="", index=True)  # 수주영업|기술지원
    stage: Mapped[str] = mapped_column(String, default="", index=True)
    category: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)  # 업무내용 multi_select
    estimated_amount: Mapped[float | None] = mapped_column(Float, nullable=True)  # 견적금액
    probability: Mapped[float | None] = mapped_column(Float, nullable=True)  # 수주확률 0~100 (PM 직접 입력)
    is_bid: Mapped[bool] = mapped_column(Boolean, default=False)
    # 의뢰처(clients DB relation 첫번째) — text 빠른 join 용도. 정식 join은 mirror_clients
    client_id: Mapped[str] = mapped_column(String, default="", index=True)
    gross_floor_area: Mapped[float | None] = mapped_column(Float, nullable=True)  # 연면적 ㎡
    floors_above: Mapped[float | None] = mapped_column(Float, nullable=True)  # 지상층수
    floors_below: Mapped[float | None] = mapped_column(Float, nullable=True)  # 지하층수
    building_count: Mapped[float | None] = mapped_column(Float, nullable=True)  # 동수
    note: Mapped[str] = mapped_column(Text, default="")
    submission_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    vat_inclusive: Mapped[str] = mapped_column(String, default="")  # 별도|포함
    performance_design_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_tunnel_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    converted_project_id: Mapped[str] = mapped_column(String, default="", index=True)
    location: Mapped[str] = mapped_column(String, default="")  # 영업 위치 (영업 row 단위)
    assignees: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    # 견적서 작성 툴 (PR5) — 문서번호 {YY}-{MM}-{NNN} 형식, 입력값+산출결과 dump
    quote_doc_number: Mapped[str] = mapped_column(String, default="", index=True)
    quote_form_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    # 견적서 종류 (PR-Q1) — 빈 값이면 '구조설계' fallback
    quote_type: Mapped[str] = mapped_column(String, default="", index=True)
    properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    url: Mapped[str] = mapped_column(String, default="")
    created_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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
