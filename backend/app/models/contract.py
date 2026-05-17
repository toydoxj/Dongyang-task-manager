"""계약서 (Contract) 도메인 — 프로젝트별 다중 계약서 메타 + Drive 파일.

PR-FH/1: 신규 SQLAlchemy 테이블. 노션 mirror 없음 (Postgres + Drive only).
1 프로젝트 → N 계약서 (원계약/변경계약/부속합의 등). 파일은 NAVER WORKS Drive
`[계약서]/{프로젝트 CODE}/{원본 filename}`에 저장.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from pydantic import BaseModel, ConfigDict
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Contract(Base):
    __tablename__ = "contracts"
    __table_args__ = (
        CheckConstraint(
            "amount IS NULL OR amount >= 0", name="contracts_amount_nonneg"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 프로젝트 page_id. mirror_projects.page_id를 가리키지만 FK는 안 검 — mirror는
    # sync로 채워지고 archived flag로 soft delete라 hard FK는 정합성 부담 큼.
    project_id: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String, nullable=False, default="")
    signed_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # 원 단위 (VAT 별도/포함은 vat_included로 구분). BigInteger — 큰 금액 대비.
    amount: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    vat_included: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # NAVER WORKS Drive 파일 메타 — 메타 row 생성 시 None, 파일 업로드 후 채워짐.
    drive_file_id: Mapped[str | None] = mapped_column(String, nullable=True)
    drive_url: Mapped[str | None] = mapped_column(String, nullable=True)
    file_name: Mapped[str | None] = mapped_column(String, nullable=True)
    uploaded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


# ── Pydantic ──


class ContractOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: str
    title: str
    signed_date: date | None = None
    start_date: date | None = None
    end_date: date | None = None
    amount: int | None = None
    vat_included: bool = False
    drive_file_id: str | None = None
    drive_url: str | None = None
    file_name: str | None = None
    uploaded_at: datetime | None = None
    note: str = ""
    created_by: int | None = None
    created_at: datetime
    updated_at: datetime
    # 응답 편의 — 라우터에서 mirror_projects join으로 채움
    project_code: str | None = None
    project_name: str | None = None
    client_id: str | None = None
    client_name: str | None = None


class ContractListResponse(BaseModel):
    items: list[ContractOut]
    count: int


class ContractCreate(BaseModel):
    project_id: str
    title: str = "원계약서"
    signed_date: date | None = None
    start_date: date | None = None
    end_date: date | None = None
    amount: int | None = None
    vat_included: bool = False
    note: str = ""


class ContractUpdate(BaseModel):
    """None 필드는 변경 안 함."""

    title: str | None = None
    signed_date: date | None = None
    start_date: date | None = None
    end_date: date | None = None
    amount: int | None = None
    vat_included: bool | None = None
    note: str | None = None
