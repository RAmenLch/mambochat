"""v_1_4_1_group_mail_attachments

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-08-22 09:00:00.000000

群组邮件附件：
- GroupMail 新增 attachments JSON 列，存放附件引用快照（统一指向中心库 File.id）。
- 新增 FileManagementType.GROUP_MAIL_ATTACHMENT 管理类型（仅 Python 枚举，无表结构变更），
  用于群组邮件附件的生命周期管理（孤儿清理）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, Sequence[str], None] = 'e6f7a8b9c0d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('GroupMail', sa.Column('attachments', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('GroupMail', 'attachments')
