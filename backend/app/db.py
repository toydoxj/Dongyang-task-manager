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


def _connect_args() -> dict:
    if _is_sqlite:
        return {"check_same_thread": False}
    # Supabase PgBouncer (transaction mode, port 6543)는 prepared statements 미지원
    # → psycopg3의 prepare_threshold=None 으로 비활성화. 또한 statement cache 크기 0.
    return {"prepare_threshold": None}


engine = create_engine(
    _db_url,
    connect_args=_connect_args(),
    # Supabase 풀러는 idle 연결을 끊을 수 있으므로 ping 으로 stale 방지
    pool_pre_ping=not _is_sqlite,
    # Postgres pool 튜닝 (sqlite는 의미 없음)
    # default(5/10)는 sync 시점의 동시 요청 누적에 약함 → pool 고갈로 hang.
    # PgBouncer transaction mode 와 호환되며 Render Starter 부하에 충분.
    pool_size=10 if not _is_sqlite else 5,
    max_overflow=20 if not _is_sqlite else 10,
    pool_timeout=20,    # 대기 20초 후 fail → SWR retry로 폭주 방지
    pool_recycle=300,   # PgBouncer가 idle 5분 후 끊는 connection 재사용 회피
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
    """테이블 생성 (개발/테스트용 — 운영에서는 Alembic 사용).

    SQLite에서는 mirror_*의 ARRAY/JSONB가 컴파일되지 않으므로 비-mirror 테이블만 생성.
    운영(Postgres)에서는 모든 테이블 생성.
    """
    # 모든 모델을 import해 Base.metadata에 등록되도록 한다
    from app.models import auth, employee, mirror  # noqa: F401

    if _is_sqlite:
        tables = [
            t
            for t in Base.metadata.tables.values()
            if not t.name.startswith("mirror_")
        ]
        Base.metadata.create_all(bind=engine, tables=tables)
    else:
        Base.metadata.create_all(bind=engine)
