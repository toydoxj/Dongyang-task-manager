"""사용자 인증 ORM + Pydantic 스키마."""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    password: Mapped[str] = mapped_column(String, nullable=False)  # bcrypt
    name: Mapped[str] = mapped_column(String, default="")
    email: Mapped[str] = mapped_column(String, default="", index=True)
    # "admin" | "team_lead" | "member"  (이전 "user"는 마이그레이션으로 "member"로 변환)
    role: Mapped[str] = mapped_column(String, default="member")
    status: Mapped[str] = mapped_column(String, default="active")  # active|pending|rejected
    session_id: Mapped[str] = mapped_column(String, default="")
    notion_user_id: Mapped[str] = mapped_column(String, default="")
    # MIDAS Electron 앱 사용자별 설정 (동양구조 웹은 미사용, MIDAS만 읽음)
    midas_url: Mapped[str] = mapped_column(String, default="")
    midas_key: Mapped[str] = mapped_column(String, default="")
    work_dir: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ── Pydantic 스키마 ──


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    name: str = ""
    email: EmailStr | str = ""


class UserInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    name: str = ""
    email: str = ""
    role: str = "member"
    status: str = "active"
    notion_user_id: str = ""
    # MIDAS 사용자 설정 — midas_key 자체는 응답에 노출하지 않음 (보안)
    midas_url: str = ""
    has_midas_key: bool = False
    work_dir: str = ""
    last_login_at: datetime | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo


class UserUpdateRequest(BaseModel):
    name: str | None = None
    email: EmailStr | str | None = None
    password: str | None = None
    notion_user_id: str | None = None
    midas_url: str | None = None
    midas_key: str | None = None
    work_dir: str | None = None
