"""contracts_table — PR-FH/1 (계약서 관리 도메인 신설).

production DB와 model metadata 사이의 누락된 index/제거 안 된 테이블 등 false-positive
변경은 모두 제거하고 contracts 테이블 신설만 남김.

Revision ID: 13ec7a9cd151
Revises: dfaa8ac3a04b
Create Date: 2026-05-17 11:19:27.877093
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "13ec7a9cd151"
down_revision: Union[str, Sequence[str], None] = "dfaa8ac3a04b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contracts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("signed_date", sa.Date(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("amount", sa.BigInteger(), nullable=True),
        sa.Column("vat_included", sa.Boolean(), nullable=False),
        sa.Column("drive_file_id", sa.String(), nullable=True),
        sa.Column("drive_url", sa.String(), nullable=True),
        sa.Column("file_name", sa.String(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "amount IS NULL OR amount >= 0", name="contracts_amount_nonneg"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_contracts_project_id"), "contracts", ["project_id"], unique=False
    )
    op.create_index(
        op.f("ix_contracts_signed_date"), "contracts", ["signed_date"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_contracts_signed_date"), table_name="contracts")
    op.drop_index(op.f("ix_contracts_project_id"), table_name="contracts")
    op.drop_table("contracts")
