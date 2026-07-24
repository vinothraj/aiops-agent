"""add_instance_id

Revision ID: 01fe03654d2e
Revises: d46688439da1
Create Date: 2026-07-09 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '01fe03654d2e'
down_revision: Union[str, None] = 'd46688439da1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('log_files', sa.Column('instance_id', sa.String(length=100), nullable=True))
    op.create_index(op.f('ix_log_files_instance_id'), 'log_files', ['instance_id'], unique=False)

    op.add_column('logs', sa.Column('instance_id', sa.String(length=100), nullable=True))
    op.create_index(op.f('ix_logs_instance_id'), 'logs', ['instance_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_logs_instance_id'), table_name='logs')
    op.drop_column('logs', 'instance_id')

    op.drop_index(op.f('ix_log_files_instance_id'), table_name='log_files')
    op.drop_column('log_files', 'instance_id')
