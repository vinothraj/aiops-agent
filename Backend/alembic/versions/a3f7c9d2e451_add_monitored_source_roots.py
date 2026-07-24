"""add_monitored_source_roots

Revision ID: a3f7c9d2e451
Revises: 01fe03654d2e
Create Date: 2026-07-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f7c9d2e451'
down_revision: Union[str, None] = '01fe03654d2e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'monitored_source_roots',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('path', sa.String(length=1024), nullable=False),
        sa.Column('label', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('last_checked_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_monitored_source_roots_id'), 'monitored_source_roots', ['id'], unique=False)
    op.create_index(op.f('ix_monitored_source_roots_path'), 'monitored_source_roots', ['path'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_monitored_source_roots_path'), table_name='monitored_source_roots')
    op.drop_index(op.f('ix_monitored_source_roots_id'), table_name='monitored_source_roots')
    op.drop_table('monitored_source_roots')
