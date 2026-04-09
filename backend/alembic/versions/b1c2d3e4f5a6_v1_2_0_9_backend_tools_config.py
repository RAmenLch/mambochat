"""v_1_2_0_9_backend_tools_config

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f6
Create Date: 2026-04-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add tools_config to BackendConfig and defaultBackendId to Agent."""
    op.add_column('BackendConfig', sa.Column('tools_config', sa.JSON(), nullable=True))
    op.add_column('Agent', sa.Column('defaultBackendId', sa.String(length=36), nullable=True))


def downgrade() -> None:
    """Remove tools_config and defaultBackendId."""
    op.drop_column('Agent', 'defaultBackendId')
    op.drop_column('BackendConfig', 'tools_config')
