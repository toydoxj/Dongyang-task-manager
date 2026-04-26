"""SQLAlchemy 데이터베이스 초기화 — Postgres(prod) / SQLite(dev fallback)."""
from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.settings import get_settings

_settings = get_settings()


def _normalize_db_url(url: str) -> str:
    """Heroku/Supabase 스타일 'postgres://' → SQLAlchemy 'postgresql+psycopg://'."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://") and "+" not in url.split("://", 1)[0]:
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


_db_url = _normalize_db_url(_settings.database_url)

# SQLite 파일 경로 디렉토리 보장
if _db_url.startswith("sqlite:///"):
    _db_path = _db_url.removeprefix("sqlite:///")
    _db_dir = os.path.dirname(os.path.abspath(_db_path))
    if _db_dir:
        os.makedirs(_db_dir, exist_ok=True)

_is_sqlite = _db_url.startswith("sqlite")

engine = create_engine(
    _db_url,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    # Supabase 풀러는 idle 연결을 끊을 수 있으므로 ping 으로 stale 방지
    pool_pre_ping=not _is_sqlite,
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
    from app.models import auth, employee, mirror  # noqa: F401

    Base.metadata.create_all(bind=engine)
