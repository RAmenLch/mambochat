"""v_1_4_5_image_gen_model_backend

Revision ID: j4f5a6b7c8d9
Revises: i2d3e4f5a6b7
Create Date: 2026-11-02 10:00:00.000000

ImageGenConfig 支持两种后端：

* ``backendType`` —— ``mcp``（原行为，存量配置一律刷成它）/ ``model``
  （绑定系统里能出图的 Chat 模型）；
* ``aiModelId`` —— 模型后端的绑定目标（``AIModel.id``）；
* ``supportsReferenceImages`` —— 参考图能力三态（NULL=自动探测 / True / False）。

同时把 ``mcpServerId`` 改为可空（模型后端不绑定 MCP 服务）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'j4f5a6b7c8d9'
down_revision: Union[str, Sequence[str], None] = 'i2d3e4f5a6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('ImageGenConfig') as batch_op:
        batch_op.add_column(
            sa.Column(
                'backendType',
                sa.String(length=20),
                nullable=False,
                server_default='mcp',
            )
        )
        batch_op.add_column(
            sa.Column('aiModelId', sa.String(length=36), nullable=True)
        )
        batch_op.add_column(
            sa.Column('supportsReferenceImages', sa.Boolean(), nullable=True)
        )
        batch_op.alter_column(
            'mcpServerId',
            existing_type=sa.String(length=36),
            nullable=True,
        )
        batch_op.create_index(
            'ix_ImageGenConfig_aiModelId', ['aiModelId'], unique=False
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('ImageGenConfig') as batch_op:
        batch_op.drop_index('ix_ImageGenConfig_aiModelId')
        batch_op.alter_column(
            'mcpServerId',
            existing_type=sa.String(length=36),
            nullable=False,
        )
        batch_op.drop_column('supportsReferenceImages')
        batch_op.drop_column('aiModelId')
        batch_op.drop_column('backendType')
