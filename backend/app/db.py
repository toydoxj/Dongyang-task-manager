"""SQLAlchemy 데이터베이스 초기화 — Postgres(prod) / SQLite(dev fallback)."""
from __future__ import annotations

import logging
import os
import time
from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine, event
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
    # PR-AQ: connection이 풀에 반환될 때 rollback 강제. read-only 라우트가
    # commit 안 하고 끝나도 "idle in transaction" 상태로 Supavisor가 점유
    # 유지하는 leak을 차단. SQLAlchemy 기본값이지만 명시적으로 표기.
    pool_reset_on_return="rollback",
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# PR-CR: SQL 실행 시간 + pool checkout wait 분리 계측 (운영 slow 진단용).
# /api/cashflow, /api/projects 등 mirror DB endpoint 2~3초 원인 분석:
# (a) SQL 자체 시간이 큰지 (b) connection checkout wait가 큰지 분리.
# slow log threshold 0.5s — codex 권장.
_SQL_SLOW_S = 0.5
_CHECKOUT_SLOW_S = 0.3
_perf_logger = logging.getLogger("db.perf")


@event.listens_for(engine, "before_cursor_execute")
def _sql_before(
    conn: Any, _cursor: Any, _statement: str, _params: Any, context: Any, _exec: Any
) -> None:
    context._dy_sql_start = time.monotonic()


@event.listens_for(engine, "after_cursor_execute")
def _sql_after(
    _conn: Any, _cursor: Any, statement: str, _params: Any, context: Any, _exec: Any
) -> None:
    start = getattr(context, "_dy_sql_start", None)
    if start is None:
        return
    elapsed = time.monotonic() - start
    if elapsed >= _SQL_SLOW_S:
        # 첫 100자만 — params 노출 회피 (PII)
        snippet = statement.strip().split("\n", 1)[0][:100]
        _perf_logger.warning(
            "slow SQL %.0fms — %s", elapsed * 1000, snippet
        )


# PR-DA: connect 시점에 PostgreSQL session 변수 강제 설정.
# 운영 worker가 OOM/restart로 죽으면 SQLAlchemy 정리 안 됨 → Supabase pooler에
# idle in transaction 잔존 (TCP fin 인지 늦음). 5분 안에 PostgreSQL이 자동
# rollback + connection close → leak 자동 회수. ALTER lock wait 사고 회피.
# database-wide ALTER DATABASE 대신 우리 connection만 적용 (다른 사용자 무관).
@event.listens_for(engine, "connect")
def _set_session_params(dbapi_conn: Any, _conn_rec: Any) -> None:
    if _is_sqlite:
        return
    with dbapi_conn.cursor() as cur:
        # 5분 idle in transaction → 자동 rollback + connection 종료
        cur.execute("SET idle_in_transaction_session_timeout = '300s'")


@event.listens_for(engine, "checkout")
def _pool_checkout(
    _conn: Any, conn_rec: Any, _conn_proxy: Any
) -> None:
    conn_rec.info["_dy_checkout_start"] = time.monotonic()


@event.listens_for(engine, "checkin")
def _pool_checkin(_conn: Any, conn_rec: Any) -> None:
    start = conn_rec.info.pop("_dy_checkout_start", None)
    if start is None:
        return
    held = time.monotonic() - start
    # checkout~checkin이 길면 connection을 오래 점유. pool wait 유발.
    if held >= _CHECKOUT_SLOW_S:
        _perf_logger.warning("long DB connection held %.0fms", held * 1000)


class Base(DeclarativeBase):
    """모든 ORM 모델의 베이스."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI Depends용 DB 세션.

    PR-AQ: 예외 전파 시 명시 rollback. 라우트가 commit 안 하고 raise해도
    session이 "idle in transaction"으로 풀에 반환되지 않게 보장.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
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
