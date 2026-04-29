"""NAVER WORKS Drive — admin이 한 번 동의한 user OAuth 토큰을 보관.

NAVER WORKS Drive API는 user account 토큰만 받음 (Service Account JWT 미지원).
도메인 단일 admin이 한 번 file scope 동의 → access_token + refresh_token을
이 테이블에 보관 → 모든 자동 폴더 생성에 재사용 + 만료 시 refresh.

테이블 행은 항상 id=1 단일 row (singleton).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class DriveCredential(Base):
    __tablename__ = "drive_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    access_token: Mapped[str] = mapped_column(String, nullable=False, default="")
    refresh_token: Mapped[str] = mapped_column(String, nullable=False, default="")
    # 발급 시 받은 access_token 만료 시각 (UTC). 만료 60초 전부터 refresh
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    scope: Mapped[str] = mapped_column(String, default="")
    # 동의한 admin user의 식별 (감사용)
    granted_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    granted_by_email: Mapped[str] = mapped_column(String, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
