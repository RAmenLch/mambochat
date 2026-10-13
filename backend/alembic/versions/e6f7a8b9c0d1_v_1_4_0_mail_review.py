"""v_1_4_0_mail_review

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-08-21 10:00:00.000000

邮件投递审核模式：
- GroupState 新增 mailMode（auto=生成完毕自动投递；review=需用户逐封审核后投递，存量按 auto 处理）。
- GroupMail 新增 reviewedAt / rejectReason，用于记录用户审核结果；
  邮件 state 复用既有 String 列，新增 reviewing / deferred / rejected 取值，无需改类型。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6f7a8b9c0d1'
down_revision: Union[str, Sequence[str], None] = 'd5e6f7a8b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # --- GroupState: 邮件投递模式（存量群按 auto，行为不变） ---
    op.add_column(
        'GroupState',
        sa.Column('mailMode', sa.String(length=20), nullable=False, server_default='auto'),
    )

    # --- GroupMail: 审核结果 ---
    op.add_column('GroupMail', sa.Column('reviewedAt', sa.DateTime(), nullable=True))
    op.add_column('GroupMail', sa.Column('rejectReason', sa.TEXT(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('GroupMail', 'rejectReason')
    op.drop_column('GroupMail', 'reviewedAt')
    op.drop_column('GroupState', 'mailMode')
