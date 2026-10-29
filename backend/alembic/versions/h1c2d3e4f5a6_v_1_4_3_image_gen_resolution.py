"""v_1_4_3_image_gen_resolution

Revision ID: h1c2d3e4f5a6
Revises: a8b9c0d1e2f3
Create Date: 2026-10-29 10:00:00.000000

ImageGenConfig 新增默认分辨率与默认等待超时两列（对应生图标准 v2 的
`resolution` / `wait_timeout` 参数），存量配置按 1024x1024 与 0 回填，
行为与升级前保持一致。
"""from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'h1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = 'a8b9c0d1e2f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'ImageGenConfig',
        sa.Column(
            'defaultResolution',
            sa.String(length=20),
            nullable=False,
            server_default='1024x1024',
        ),
    )
    op.add_column(
        'ImageGenConfig',
        sa.Column(
            'defaultWaitTimeout',
            sa.Integer(),
            nullable=False,
            server_default='0',
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('ImageGenConfig', 'defaultWaitTimeout')
    op.drop_column('ImageGenConfig', 'defaultResolution')
