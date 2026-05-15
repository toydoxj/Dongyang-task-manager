"""모든 public 테이블 RLS enable (PR-CZ: Supabase advisor 보안 경고 조치)

Revision ID: f1d2e3f05015
Revises: e0c1d2e05015
Create Date: 2026-05-15 10:00:00.000000

Supabase advisor critical issue:
- rls_disabled_in_public — public 스키마 테이블에 Row-Level Security 비활성
- sensitive_columns_exposed — anon key + PostgREST API로 RLS 없는 테이블 노출

조치: 모든 public 테이블 RLS enable. policy는 부여하지 않음 → anon/authenticated
역할 모두 access denied. backend는 service_role(또는 superuser)로 connection
string 직접 접근하므로 RLS BYPASS — 영향 없음.

frontend는 Supabase JS client 사용 안 함 (확인 완료) — anon key 사용 흔적 0.
PostgREST API 차단으로 잠재 노출 위험 제거.

향후 클라이언트 직접 접근이 필요한 테이블이 생기면 명시 policy 부여 필요.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "f1d2e3f05015"
down_revision: Union[str, Sequence[str], None] = "e0c1d2e05015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite(test) 등은 RLS 미지원 — skip.
        return
    # public 스키마의 모든 테이블 RLS enable. alembic 메타데이터 테이블은 제외.
    op.execute(
        """
        DO $$
        DECLARE
            t TEXT;
        BEGIN
            FOR t IN
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                  AND tablename NOT LIKE 'alembic_%'
            LOOP
                EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
            END LOOP;
        END $$;
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        """
        DO $$
        DECLARE
            t TEXT;
        BEGIN
            FOR t IN
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                  AND tablename NOT LIKE 'alembic_%'
            LOOP
                EXECUTE format('ALTER TABLE public.%I DISABLE ROW LEVEL SECURITY', t);
            END LOOP;
        END $$;
        """
    )
