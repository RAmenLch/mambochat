"""v_1_4_2_image_gen_config

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-08-23 10:00:00.000000

新增生图工具配置表：一条配置绑定一个符合生图标准的 MCP 服务
（image_generate / image_task_status / image_download），并提供默认参数。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8b9c0d1e2f3'
down_revision: Union[str, Sequence[str], None] = 'f7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'ImageGenConfig',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.TEXT(), nullable=True),
        sa.Column('mcpServerId', sa.String(length=36), nullable=False),
        sa.Column('defaultCount', sa.Integer(), nullable=False),
        sa.Column('defaultSync', sa.Boolean(), nullable=False),
        sa.Column('timeout', sa.Float(), nullable=True),
        sa.Column('isEnabled', sa.Boolean(), nullable=True),
        sa.Column('createdAt', sa.DateTime(), nullable=False),
        sa.Column('updatedAt', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_index(
        'ix_ImageGenConfig_mcpServerId', 'ImageGenConfig', ['mcpServerId'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_ImageGenConfig_mcpServerId', table_name='ImageGenConfig')
    op.drop_table('ImageGenConfig')
