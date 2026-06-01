"""v_1_2_0_11_message_checkpoint_map

Revision ID: a2b3c4d5e6f7
Revises: c1d2e3f4a5b6
Create Date: 2026-05-29 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, Sequence[str], None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('message_checkpoints_map',
        sa.Column('message_id', sa.String(length=36), nullable=False),
        sa.Column('checkpoint_id', sa.String(), nullable=False),
        sa.Column('chat_id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('message_id'),
    )
    op.create_index(
        'ix_message_checkpoints_map_chat_id',
        'message_checkpoints_map',
        ['chat_id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_message_checkpoints_map_chat_id', table_name='message_checkpoints_map')
    op.drop_table('message_checkpoints_map')
