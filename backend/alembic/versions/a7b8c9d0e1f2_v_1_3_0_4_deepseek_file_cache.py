"""v_1_3_0_4_deepseek_file_cache

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-08-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """新增 DeepSeek Files API 上传缓存表。"""
    op.create_table(
        'DeepSeekFileCache',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('providerKey', sa.String(length=64), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('fileId', sa.String(length=128), nullable=False),
        sa.Column('mimeType', sa.String(length=100), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='ready'),
        sa.Column('createdAt', sa.DateTime(), nullable=False),
        sa.Column('expiresAt', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('providerKey', 'sha256', name='uq_dsf_provider_hash'),
    )


def downgrade() -> None:
    """删除 DeepSeek Files API 上传缓存表。"""
    op.drop_table('DeepSeekFileCache')
