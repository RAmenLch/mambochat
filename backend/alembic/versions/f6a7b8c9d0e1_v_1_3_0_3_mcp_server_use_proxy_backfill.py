"""v_1_3_0_3_mcp_server_use_proxy_backfill

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-10 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Backfill existing rows: useProxy NULL -> 0."""
    op.execute("UPDATE McpServer SET useProxy = 0 WHERE useProxy IS NULL")


def downgrade() -> None:
    """No-op (data backfill cannot be reversed meaningfully)."""
    pass
