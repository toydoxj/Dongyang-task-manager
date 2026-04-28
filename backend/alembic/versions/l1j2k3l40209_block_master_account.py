"""마스터 계정(dyce@dyce.kr) status를 rejected로 강등

Revision ID: l1j2k3l40209
Revises: k0i1j2k30208
Create Date: 2026-04-29 00:00:00.000000

이미 DB에 자동 생성된 dyce@dyce.kr (id=19) 같은 마스터 계정의 status를
'rejected'로 변경. SSO_BLOCKED_EMAILS 정책과 정합.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "l1j2k3l40209"
down_revision: Union[str, Sequence[str], None] = "k0i1j2k30208"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE users
        SET status = 'rejected', session_id = ''
        WHERE LOWER(email) = 'dyce@dyce.kr'
          AND status != 'rejected'
        """
    )


def downgrade() -> None:
    # 안전상 자동 복원하지 않음 (의도적으로 강등한 계정의 의도 보존)
    pass
