"""v_1_3_0_2_mcp_server_use_proxy

Revision ID: e5f6a7b8c9d0
Revises: b3c4d5e6f7a8
Create Date: 2026-08-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add useProxy column to McpServer."""
    op.add_column('McpServer', sa.Column('useProxy', sa.Boolean(), nullable=True))


def downgrade() -> None:
    """Remove useProxy column from McpServer."""
    op.drop_column('McpServer', 'useProxy')
