"""notion_outbox — PR-FO Phase 1.3.1 Transactional Outbox 인프라.

mirror-first write + 노션 push 비동기화의 기반 테이블. 호출자 변경은 별도 PR.

흐름 (다음 PR에서 활성화):
1. write endpoint이 (mirror update + outbox enqueue)를 같은 transaction에서 commit
2. 사용자에게 즉시 응답 (~50ms, 노션 round-trip 제거)
3. outbox_drain worker가 FOR UPDATE SKIP LOCKED로 배치 픽업 → 노션 push
4. 실패 시 attempts++ + exponential backoff. max 초과 시 status='dead'

Codex 자문 (2026-05-25):
- aggregate_type/aggregate_id로 도메인별 식별
- notion_page_id: create는 NULL → push 성공 시 채움
- dedupe_key: 예 'seal_requests:abc-123:v5' — 같은 transaction 두 번 enqueue 회피
- status 인덱스 + next_attempt_at 인덱스 — drain worker SELECT 효율

Revision ID: i75b02f0525
Revises: h75b02f0522
Create Date: 2026-05-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "i75b02f0525"
down_revision: Union[str, Sequence[str], None] = "h75b02f0522"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("SET LOCAL statement_timeout = 0")
    op.create_table(
        "notion_outbox",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("aggregate_type", sa.String(), nullable=False),
        sa.Column("aggregate_id", sa.String(), nullable=False),
        sa.Column("notion_page_id", sa.String(), nullable=True),
        sa.Column("op", sa.String(), nullable=False),
        sa.Column(
            "payload", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "status", sa.String(), nullable=False, server_default=sa.text("'pending'")
        ),
        sa.Column(
            "attempts", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lock_owner", sa.String(), nullable=True),
        sa.Column("dedupe_key", sa.String(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("dedupe_key", name="uq_notion_outbox_dedupe_key"),
    )
    op.create_index(
        "ix_notion_outbox_status_next",
        "notion_outbox",
        ["status", "next_attempt_at"],
    )
    op.create_index(
        "ix_notion_outbox_aggregate",
        "notion_outbox",
        ["aggregate_type", "aggregate_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_notion_outbox_aggregate", table_name="notion_outbox")
    op.drop_index("ix_notion_outbox_status_next", table_name="notion_outbox")
    op.drop_table("notion_outbox")
