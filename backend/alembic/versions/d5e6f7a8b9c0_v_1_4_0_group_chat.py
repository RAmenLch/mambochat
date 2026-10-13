"""v_1_4_0_group_chat

Revision ID: d5e6f7a8b9c0
Revises: a7b8c9d0e1f2
Create Date: 2026-08-20 12:30:00.000000

群组会话：Chat 增加 folderType / memberAlias 字段与群内成员别名唯一索引，
并新增 GroupState / GroupTask / GroupMail / GroupMailReceipt 四张表。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, Sequence[str], None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # --- Chat: 新增群标记字段 ---
    op.add_column('Chat', sa.Column('folderType', sa.String(length=20), nullable=True))
    op.add_column('Chat', sa.Column('memberAlias', sa.String(length=64), nullable=True))
    # 群内成员别名唯一（普通节点 memberAlias 为 NULL，SQLite 允许多个 NULL）
    op.create_index(
        'uq_chat_parent_member_alias',
        'Chat',
        ['parentId', 'memberAlias'],
        unique=True,
    )

    # --- GroupState ---
    op.create_table(
        'GroupState',
        sa.Column('groupId', sa.String(length=36), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='ready'),
        sa.Column('pauseReason', sa.String(length=50), nullable=True),
        sa.Column('activeTaskId', sa.String(length=36), nullable=True),
        sa.Column('autoRoundLimit', sa.Integer(), nullable=False, server_default='50'),
        sa.Column('autoRoundCount', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('nextTaskSeq', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('nextMailSeq', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('createdAt', sa.DateTime(), nullable=False),
        sa.Column('updatedAt', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('groupId'),
        sa.ForeignKeyConstraint(['groupId'], ['Chat.id'], ondelete='CASCADE'),
    )

    # --- GroupTask ---
    op.create_table(
        'GroupTask',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('groupId', sa.String(length=36), nullable=False),
        sa.Column('memberChatId', sa.String(length=36), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=30), nullable=False),
        sa.Column('state', sa.String(length=20), nullable=False),
        sa.Column('requestId', sa.String(length=64), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('baseMessageId', sa.String(length=36), nullable=True),
        sa.Column('userMessageId', sa.String(length=36), nullable=True),
        sa.Column('assistantMessageId', sa.String(length=36), nullable=True),
        sa.Column('coalesceKey', sa.String(length=80), nullable=True),
        sa.Column('snapshotReceiptIds', sa.JSON(), nullable=True),
        sa.Column('snapshotTakenAt', sa.DateTime(), nullable=True),
        sa.Column('mailReadRequested', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('attemptCount', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('startedAt', sa.DateTime(), nullable=True),
        sa.Column('finishedAt', sa.DateTime(), nullable=True),
        sa.Column('createdAt', sa.DateTime(), nullable=False),
        sa.Column('errorCode', sa.String(length=50), nullable=True),
        sa.Column('errorMessage', sa.TEXT(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['groupId'], ['Chat.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('groupId', 'sequence', name='uq_grouptask_group_sequence'),
        sa.UniqueConstraint('groupId', 'requestId', 'memberChatId', name='uq_grouptask_idem'),
        sa.UniqueConstraint('coalesceKey', name='uq_grouptask_coalesce'),
    )
    op.create_index('ix_grouptask_groupId', 'GroupTask', ['groupId'], unique=False)
    op.create_index('ix_grouptask_group_state', 'GroupTask', ['groupId', 'state'], unique=False)
    op.create_index('ix_grouptask_member', 'GroupTask', ['memberChatId'], unique=False)

    # --- GroupMail ---
    op.create_table(
        'GroupMail',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('groupId', sa.String(length=36), nullable=False),
        sa.Column('sourceTaskId', sa.String(length=36), nullable=False),
        sa.Column('senderChatId', sa.String(length=36), nullable=False),
        sa.Column('senderAliasSnapshot', sa.String(length=64), nullable=False),
        sa.Column('recipientSnapshot', sa.JSON(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=True),
        sa.Column('content', sa.TEXT(), nullable=False),
        sa.Column('toolCallId', sa.String(length=100), nullable=False),
        sa.Column('toolCallOrder', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('state', sa.String(length=20), nullable=False, server_default='staged'),
        sa.Column('sequence', sa.Integer(), nullable=True),
        sa.Column('createdAt', sa.DateTime(), nullable=False),
        sa.Column('sentAt', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['groupId'], ['Chat.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('sourceTaskId', 'toolCallId', name='uq_groupmail_task_toolcall'),
        sa.UniqueConstraint('groupId', 'sequence', name='uq_groupmail_group_sequence'),
    )
    op.create_index('ix_groupmail_groupId', 'GroupMail', ['groupId'], unique=False)
    op.create_index('ix_groupmail_sourceTaskId', 'GroupMail', ['sourceTaskId'], unique=False)
    op.create_index('ix_groupmail_group_state', 'GroupMail', ['groupId', 'state'], unique=False)

    # --- GroupMailReceipt ---
    op.create_table(
        'GroupMailReceipt',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('mailId', sa.String(length=36), nullable=False),
        sa.Column('recipientChatId', sa.String(length=36), nullable=False),
        sa.Column('readAt', sa.DateTime(), nullable=True),
        sa.Column('readByTaskId', sa.String(length=36), nullable=True),
        sa.Column('notificationTaskId', sa.String(length=36), nullable=True),
        sa.Column('createdAt', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['mailId'], ['GroupMail.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('mailId', 'recipientChatId', name='uq_gmr_mail_recipient'),
    )
    op.create_index('ix_groupmailreceipt_mailId', 'GroupMailReceipt', ['mailId'], unique=False)
    op.create_index('ix_gmr_recipient_read', 'GroupMailReceipt', ['recipientChatId', 'readAt'], unique=False)
    op.create_index('ix_gmr_notification', 'GroupMailReceipt', ['notificationTaskId'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_gmr_notification', table_name='GroupMailReceipt')
    op.drop_index('ix_gmr_recipient_read', table_name='GroupMailReceipt')
    op.drop_index('ix_groupmailreceipt_mailId', table_name='GroupMailReceipt')
    op.drop_table('GroupMailReceipt')

    op.drop_index('ix_groupmail_group_state', table_name='GroupMail')
    op.drop_index('ix_groupmail_sourceTaskId', table_name='GroupMail')
    op.drop_index('ix_groupmail_groupId', table_name='GroupMail')
    op.drop_table('GroupMail')

    op.drop_index('ix_grouptask_member', table_name='GroupTask')
    op.drop_index('ix_grouptask_group_state', table_name='GroupTask')
    op.drop_index('ix_grouptask_groupId', table_name='GroupTask')
    op.drop_table('GroupTask')

    op.drop_table('GroupState')

    op.drop_index('uq_chat_parent_member_alias', table_name='Chat')
    op.drop_column('Chat', 'memberAlias')
    op.drop_column('Chat', 'folderType')
