"""mirror_seal_requests.properties — PR-FL Phase 1.1 list_seal_requests mirror 전환.

`/api/seal-requests` GET의 노션 query_all(평시 2~3초) 호출을 제거하고
mirror SELECT(50ms 이내)로 응답하기 위해, 노션 page.properties dict 통째
저장할 JSONB 컬럼 추가. 다른 mirror(MirrorProject/Client/Sales/...)와 일관.

운영 backfill 전략:
- nullable=True + server_default 없음 → 옛 row는 NULL. app code가 `r.properties or {}`로 falsy 분기 → 빈 dict로 안전 degrade.
- write-through(create/update/approve/reject 시 즉시 `_upsert_seal_request`)와 5분 incremental cron이 자연 backfill.
- 즉시 전체 backfill 필요 시 `python -m app.scripts.sync_once --kind seal_requests --full` 수동 트리거 가능.

PR-GI/1 lock wait 패턴 답습:
- `SET LOCAL statement_timeout = 0` — 이 migration만 timeout 해제.
- ADD COLUMN ... JSONB nullable은 PostgreSQL 11+ metadata only (rewrite 없음, 즉시 완료).

Revision ID: h75b02f0522
Revises: g75b02f0519
Create Date: 2026-05-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "h75b02f0522"
down_revision: Union[str, Sequence[str], None] = "g75b02f0519"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("SET LOCAL statement_timeout = 0")
    op.add_column(
        "mirror_seal_requests",
        sa.Column("properties", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("mirror_seal_requests", "properties")
