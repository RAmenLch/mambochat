"""v130_add_chat_web_search_mode

Revision ID: b2f1e4d6a8c0
Revises: a2b3c4d5e6f7
Create Date: 2026-07-08 18:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2f1e4d6a8c0'
down_revision: Union[str, Sequence[str], None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('Chat', sa.Column('web_search_mode', sa.String(20), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('Chat', 'web_search_mode')
