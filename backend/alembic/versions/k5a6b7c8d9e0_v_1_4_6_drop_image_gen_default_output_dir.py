"""v_1_4_6_drop_image_gen_default_output_dir

Revision ID: k5a6b7c8d9e0
Revises: j4f5a6b7c8d9
Create Date: 2026-11-05 16:00:00.000000

清掉 ``ImageGenConfig.defaultOutputDir`` 这个历史遗留列。

该列在早期版本里曾被模型声明过（落盘目录由配置固定），后来改为「目录由 LLM 通过
``image_download.path`` 指定」时从模型里删除，但 SQLite 上没有任何迁移把它 drop 掉，
于是留在库里的是一列 ``NOT NULL`` 且**没有 server default** 的僵尸列——只要插入
新配置就会 ``NOT NULL constraint failed``。这里把它彻底删除（列已无任何代码引用）。

列不存在时（全新库）直接跳过，保证幂等。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'k5a6b7c8d9e0'
down_revision: Union[str, Sequence[str], None] = 'j4f5a6b7c8d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = 'ImageGenConfig'
LEGACY_COLUMN = 'defaultOutputDir'


def _has_column(column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(col['name'] == column for col in inspector.get_columns(TABLE))


def upgrade() -> None:
    """Upgrade schema."""
    if not _has_column(LEGACY_COLUMN):
        return
    with op.batch_alter_table(TABLE) as batch_op:
        batch_op.drop_column(LEGACY_COLUMN)


def downgrade() -> None:
    """Downgrade schema."""
    if _has_column(LEGACY_COLUMN):
        return
    with op.batch_alter_table(TABLE) as batch_op:
        batch_op.add_column(
            sa.Column(LEGACY_COLUMN, sa.String(length=500), nullable=True)
        )
