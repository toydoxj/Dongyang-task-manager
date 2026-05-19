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
    # PR-GI/1 fix: 직전 deploy에서 NOT NULL + DEFAULT 추가가 statement_timeout으로
    # 취소됨 (idle-in-transaction 또는 lock wait). nullable로 완화 +
    # statement_timeout=0 (이 migration만)으로 안전 보장.
    # 옛 row는 NULL이 들어가도 app code가 falsy 분기(`if proj.contract_folder_id`)로
    # cache miss 흐름 동일 — 데이터 회귀 없음.
    op.execute("SET LOCAL statement_timeout = 0")
    op.add_column(
        "mirror_projects",
        sa.Column(
            "contract_folder_id",
            sa.String(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("mirror_projects", "contract_folder_id")
