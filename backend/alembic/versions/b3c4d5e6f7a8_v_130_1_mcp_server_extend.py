"""v_130_1_mcp_server_extend

Revision ID: b3c4d5e6f7a8
Revises: b2f1e4d6a8c0
Create Date: 2026-07-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, Sequence[str], None] = 'b2f1e4d6a8c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add headers, timeout, sse_read_timeout, cwd to McpServer."""
    op.add_column('McpServer', sa.Column('headers', sa.JSON(), nullable=True))
    op.add_column('McpServer', sa.Column('timeout', sa.Float(), nullable=True))
    op.add_column('McpServer', sa.Column('sse_read_timeout', sa.Float(), nullable=True))
    op.add_column('McpServer', sa.Column('cwd', sa.String(length=500), nullable=True))


def downgrade() -> None:
    """Remove headers, timeout, sse_read_timeout, cwd from McpServer."""
    op.drop_column('McpServer', 'cwd')
    op.drop_column('McpServer', 'sse_read_timeout')
    op.drop_column('McpServer', 'timeout')
    op.drop_column('McpServer', 'headers')
