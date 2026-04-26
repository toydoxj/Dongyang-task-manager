"""직원 마스터 ORM + Pydantic 스키마.

엑셀로 1차 import 후 admin이 보강 편집. 회원가입 시 email로 매칭하여 user.id 연결.
민감정보(연봉/실적 등)는 절대 저장하지 않는다 — import 화이트리스트로 차단.
"""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    position: Mapped[str] = mapped_column(String, default="")  # 직급
    team: Mapped[str] = mapped_column(String, default="")  # 소속(부서/팀)
    degree: Mapped[str] = mapped_column(String, default="")
    license: Mapped[str] = mapped_column(String, default="")
    grade: Mapped[str] = mapped_column(String, default="")  # 등급(특/고/중/초)
    email: Mapped[str] = mapped_column(String, default="", index=True)
    # 계정과 연결되면 채워짐 (회원가입 시 자동 매칭 또는 admin 수동)
    linked_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )


# ── Pydantic ──


class EmployeeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    position: str = ""
    team: str = ""
    degree: str = ""
    license: str = ""
    grade: str = ""
    email: str = ""
    linked_user_id: int | None = None


class EmployeeListResponse(BaseModel):
    items: list[EmployeeOut]
    count: int


class EmployeeUpdate(BaseModel):
    name: str | None = None
    position: str | None = None
    team: str | None = None
    degree: str | None = None
    license: str | None = None
    grade: str | None = None
    email: EmailStr | str | None = None


class EmployeeCreate(BaseModel):
    name: str
    position: str = ""
    team: str = ""
    degree: str = ""
    license: str = ""
    grade: str = ""
    email: str = ""


class EmployeeImportResult(BaseModel):
    inserted: int
    updated: int
    skipped: int
    total_rows: int
