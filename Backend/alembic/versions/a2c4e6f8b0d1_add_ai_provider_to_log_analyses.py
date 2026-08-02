"""add_ai_provider_to_log_analyses

Revision ID: a2c4e6f8b0d1
Revises: f1b2c3d4e5a6
Create Date: 2026-08-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2c4e6f8b0d1'
down_revision: Union[str, None] = 'f1b2c3d4e5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('log_analyses', sa.Column('ai_provider', sa.String(length=50), nullable=True))
    op.add_column('log_analyses', sa.Column('ai_model', sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column('log_analyses', 'ai_model')
    op.drop_column('log_analyses', 'ai_provider')
