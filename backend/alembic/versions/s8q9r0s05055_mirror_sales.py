"""mirror_sales 테이블 추가 — 영업(수주영업+기술지원) 미러

Revision ID: s8q9r0s05055
Revises: r7p8q9r05044
Create Date: 2026-05-05 12:00:00.000000

사장이 운영하던 '견적서 작성 리스트' 노션 DB의 미러. kind 컬럼으로 수주영업/
기술지원을 구분하고, 두 갈래의 단계를 한 stage select에 합쳐 표현한다.
category/assignees는 multi_select라 ARRAY[String] 으로 모델링.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision: str = "s8q9r0s05055"
down_revision: Union[str, Sequence[str], None] = "r7p8q9r05044"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mirror_sales",
        sa.Column("page_id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False, server_default=""),
        sa.Column("kind", sa.String(), nullable=False, server_default=""),
        sa.Column("stage", sa.String(), nullable=False, server_default=""),
        sa.Column(
            "category",
            ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
        sa.Column("estimated_amount", sa.Float(), nullable=True),
        sa.Column(
            "is_bid", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("client_id", sa.String(), nullable=False, server_default=""),
        sa.Column("gross_floor_area", sa.Float(), nullable=True),
        sa.Column("floors_above", sa.Float(), nullable=True),
        sa.Column("floors_below", sa.Float(), nullable=True),
        sa.Column("building_count", sa.Float(), nullable=True),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("submission_date", sa.Date(), nullable=True),
        sa.Column("vat_inclusive", sa.String(), nullable=False, server_default=""),
        sa.Column("performance_design_amount", sa.Float(), nullable=True),
        sa.Column("wind_tunnel_amount", sa.Float(), nullable=True),
        sa.Column("parent_lead_id", sa.String(), nullable=False, server_default=""),
        sa.Column(
            "converted_project_id", sa.String(), nullable=False, server_default=""
        ),
        sa.Column(
            "assignees",
            ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
        sa.Column(
            "properties",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("url", sa.String(), nullable=False, server_default=""),
        sa.Column("created_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_edited_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # 단일 컬럼 B-tree 인덱스 — 자주 필터/정렬되는 컬럼만
    op.create_index("ix_mirror_sales_kind", "mirror_sales", ["kind"])
    op.create_index("ix_mirror_sales_stage", "mirror_sales", ["stage"])
    op.create_index("ix_mirror_sales_client_id", "mirror_sales", ["client_id"])
    op.create_index(
        "ix_mirror_sales_parent_lead_id", "mirror_sales", ["parent_lead_id"]
    )
    op.create_index(
        "ix_mirror_sales_converted_project_id",
        "mirror_sales",
        ["converted_project_id"],
    )
    op.create_index(
        "ix_mirror_sales_last_edited_time", "mirror_sales", ["last_edited_time"]
    )
    op.create_index(
        "ix_mirror_sales_submission_date", "mirror_sales", ["submission_date"]
    )
    op.create_index("ix_mirror_sales_archived", "mirror_sales", ["archived"])
    # ARRAY 컬럼 GIN — /me 페이지에서 assignees @> [본인] 필터, 카테고리 필터에 사용
    op.execute(
        'CREATE INDEX IF NOT EXISTS "ix_mirror_sales_assignees_gin" '
        'ON "mirror_sales" USING GIN ("assignees")'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS "ix_mirror_sales_category_gin" '
        'ON "mirror_sales" USING GIN ("category")'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS "ix_mirror_sales_category_gin"')
    op.execute('DROP INDEX IF EXISTS "ix_mirror_sales_assignees_gin"')
    op.drop_index("ix_mirror_sales_archived", table_name="mirror_sales")
    op.drop_index("ix_mirror_sales_submission_date", table_name="mirror_sales")
    op.drop_index("ix_mirror_sales_last_edited_time", table_name="mirror_sales")
    op.drop_index(
        "ix_mirror_sales_converted_project_id", table_name="mirror_sales"
    )
    op.drop_index("ix_mirror_sales_parent_lead_id", table_name="mirror_sales")
    op.drop_index("ix_mirror_sales_client_id", table_name="mirror_sales")
    op.drop_index("ix_mirror_sales_stage", table_name="mirror_sales")
    op.drop_index("ix_mirror_sales_kind", table_name="mirror_sales")
    op.drop_table("mirror_sales")
