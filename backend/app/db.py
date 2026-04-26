"""SQLAlchemy + SQLite 데이터베이스 초기화."""
from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.settings import get_settings

_settings = get_settings()
_db_url = _settings.database_url

# SQLite 파일 경로 디렉토리 보장
if _db_url.startswith("sqlite:///"):
    _db_path = _db_url.removeprefix("sqlite:///")
    _db_dir = os.path.dirname(os.path.abspath(_db_path))
    if _db_dir:
        os.makedirs(_db_dir, exist_ok=True)

engine = create_engine(
    _db_url,
    connect_args={"check_same_thread": False} if _db_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """모든 ORM 모델의 베이스."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI Depends용 DB 세션."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """테이블 생성 (개발/테스트용 — 운영에서는 Alembic 사용)."""
    # 모든 모델을 import해 Base.metadata에 등록되도록 한다
    from app.models import auth  # noqa: F401

    Base.metadata.create_all(bind=engine)
