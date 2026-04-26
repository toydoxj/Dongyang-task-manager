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
    role: Mapped[str] = mapped_column(String, default="user")  # "admin" | "user"
    status: Mapped[str] = mapped_column(String, default="active")  # active|pending|rejected
    session_id: Mapped[str] = mapped_column(String, default="")
    notion_user_id: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


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
    role: str = "user"
    status: str = "active"
    notion_user_id: str = ""


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo


class UserUpdateRequest(BaseModel):
    name: str | None = None
    email: EmailStr | str | None = None
    password: str | None = None
    notion_user_id: str | None = None
