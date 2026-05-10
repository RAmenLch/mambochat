"""v1_2_0_10_add_chunk_error_message

Revision ID: c1d2e3f4a5b6
Revises: b1c2d3e4f5a6
Create Date: 2026-05-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add error_message column to ResourceKBChunk."""
    op.add_column('ResourceKBChunk', sa.Column('error_message', sa.TEXT(), nullable=True))


def downgrade() -> None:
    """Remove error_message column from ResourceKBChunk."""
    op.drop_column('ResourceKBChunk', 'error_message')
