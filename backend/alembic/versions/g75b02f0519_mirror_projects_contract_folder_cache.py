"""mirror_projects.contract_folder_id — PR-GI/1 Drive sub-folder fileId 캐시.

매 계약서 업로드 시 "6. 계약서" sub-folder를 list_children으로 매번 resolve하던
것을 mirror_projects 컬럼에 캐싱 → 두 번째 업로드부터 ~2초 절감.

server_default=""로 옛 row backward-compat. cache miss 시 sso_drive로 resolve.

Revision ID: g75b02f0519
Revises: 75b02f886038
Create Date: 2026-05-19 11:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "g75b02f0519"
down_revision: Union[str, Sequence[str], None] = "75b02f886038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mirror_projects",
        sa.Column(
            "contract_folder_id",
            sa.String(),
            nullable=False,
            server_default="",
        ),
    )


def downgrade() -> None:
    op.drop_column("mirror_projects", "contract_folder_id")
