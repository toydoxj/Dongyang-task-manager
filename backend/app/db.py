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
    # Postgres pool 튜닝 (sqlite는 의미 없음).
    # 2026-05-12: 운영 중 connection leak으로 Supavisor session pool(50) 도달
    # 사고 발생. SQLAlchemy 풀을 작게 두어 leak 누적 속도를 늦추고, 빠른
    # recycle로 idle connection이 풀에 묶여 있는 시간을 줄인다.
    # 워커 1개 기준: 최대 15 connection. Supavisor 50 안에 충분히 들어감.
    pool_size=5 if not _is_sqlite else 5,
    max_overflow=10 if not _is_sqlite else 10,
    pool_timeout=20,    # 대기 20초 후 fail → SWR retry로 폭주 방지
    pool_recycle=120,   # 2분 후 강제 재사용 reset — idle leak 빠른 회수
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

    SQLite에서는 ARRAY/JSONB 사용 테이블이 컴파일되지 않으므로 제외.
    운영(Postgres)에서는 모든 테이블 생성.
    """
    # 모든 모델을 import해 Base.metadata에 등록되도록 한다
    from app.models import (  # noqa: F401
        auth,
        calendar_event,
        drive_creds,
        employee,
        mirror,
        snapshot,
        weekly_publish,
    )

    if _is_sqlite:
        # ARRAY/JSONB 사용 테이블은 SQLite 호환 안 됨
        skip_tables = {"project_snapshots"}
        tables = [
            t
            for t in Base.metadata.tables.values()
            if not t.name.startswith("mirror_") and t.name not in skip_tables
        ]
        Base.metadata.create_all(bind=engine, tables=tables)
    else:
        Base.metadata.create_all(bind=engine)
