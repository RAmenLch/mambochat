"""v1.2.0_file_storage_enhancement

Revision ID: 923ee239d567
Revises: 4442b0f1e406
Create Date: 2026-03-03 17:07:44.279380

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '923ee239d567'
down_revision: Union[str, Sequence[str], None] = '4442b0f1e406'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 只需要添加列，不需要操作约束，因为原本就已经存在了
    op.add_column('File', sa.Column('storage_type', sa.String(length=20), nullable=False, server_default='local'))
    op.add_column('File', sa.Column('content', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # 同样去掉约束的删除操作
    op.drop_column('File', 'content')
    op.drop_column('File', 'storage_type')

