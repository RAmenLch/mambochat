"""v_1_4_4_image_gen_tool_mode

Revision ID: i2d3e4f5a6b7
Revises: h1c2d3e4f5a6
Create Date: 2026-10-30 10:00:00.000000

ImageGenConfig 新增两个工具集开关：

* ``enableStandardTools`` —— 契约三件套（image_generate / image_task_status /
  image_download），存量配置一律开启，升级后行为不变；
* ``enableGenerateShow`` —— 平台侧一条龙工具 image_generate_show，存量配置
  默认关闭，避免升级后突然向已有 Agent 暴露新工具。

两者至少开启一个，由接口层校验。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'i2d3e4f5a6b7'
down_revision: Union[str, Sequence[str], None] = 'h1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'ImageGenConfig',
        sa.Column(
            'enableStandardTools',
            sa.Boolean(),
            nullable=False,
            server_default='1',
        ),
    )
    op.add_column(
        'ImageGenConfig',
        sa.Column(
            'enableGenerateShow',
            sa.Boolean(),
            nullable=False,
            server_default='0',
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('ImageGenConfig', 'enableGenerateShow')
    op.drop_column('ImageGenConfig', 'enableStandardTools')
