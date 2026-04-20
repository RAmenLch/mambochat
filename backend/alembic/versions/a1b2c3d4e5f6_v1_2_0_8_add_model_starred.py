"""v1.2.0.8: add starred column to AIModel

Revision ID: a1b2c3d4e5f6
Revises: 04f04e99c0b8
Create Date: 2026-04-08
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = '04f04e99c0b8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('AIModel', sa.Column('starred', sa.Boolean(), nullable=False, server_default=sa.text('0')))


def downgrade() -> None:
    op.drop_column('AIModel', 'starred')
