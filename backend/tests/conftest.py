"""테스트 공통 fixture.

- 모든 테스트가 단일 SQLite 파일 + 단일 SQLAlchemy engine 공유
  (engine은 db.py import 시 한 번만 생성되므로 DATABASE_URL을 테스트마다 바꿀 수 없음)
- 매 테스트마다 users / employees 테이블만 truncate해 격리
- 매 테스트마다 lru_cache된 Settings 무효화 (works 관련 환경변수 변경 반영)
"""
from __future__ import annotations

import os
import tempfile

# db.py / settings.py가 import되기 전에 환경변수 확정
_TMP = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP.close()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMP.name}")
os.environ.setdefault("JWT_SECRET", "test-secret")

import pytest  # noqa: E402

from app.settings import get_settings  # noqa: E402


@pytest.fixture(autouse=True)
def _settings_cache_clear():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _truncate_user_tables():
    """매 테스트 격리. 테이블이 아직 없으면 무시."""
    from app.db import SessionLocal, engine, init_db
    from sqlalchemy import inspect

    init_db()  # 테이블 보장 (멱등)
    db = SessionLocal()
    try:
        insp = inspect(engine)
        for table in ("users", "employees"):
            if insp.has_table(table):
                db.execute(__import__("sqlalchemy").text(f"DELETE FROM {table}"))
        db.commit()
    finally:
        db.close()
    yield
