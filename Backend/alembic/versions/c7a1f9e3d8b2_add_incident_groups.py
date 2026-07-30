"""add_incident_groups

Revision ID: c7a1f9e3d8b2
Revises: a3f7c9d2e451
Create Date: 2026-07-25 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7a1f9e3d8b2'
down_revision: Union[str, None] = 'a3f7c9d2e451'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('incident_groups',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('fingerprint', sa.String(length=64), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('root_cause_category', sa.String(length=100), nullable=False),
    sa.Column('representative_analysis_id', sa.Integer(), nullable=True),
    sa.Column('occurrence_count', sa.Integer(), nullable=False, server_default='1'),
    sa.Column('status', sa.String(length=50), nullable=False, server_default='ACTIVE'),
    sa.Column('first_seen_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    sa.Column('last_seen_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    sa.ForeignKeyConstraint(['representative_analysis_id'], ['log_analyses.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('fingerprint')
    )
    op.create_index(op.f('ix_incident_groups_id'), 'incident_groups', ['id'], unique=False)
    op.create_index(op.f('ix_incident_groups_fingerprint'), 'incident_groups', ['fingerprint'], unique=True)
    op.create_index(op.f('ix_incident_groups_root_cause_category'), 'incident_groups', ['root_cause_category'], unique=False)

    op.add_column('log_analyses', sa.Column('incident_group_id', sa.Integer(), nullable=True))
    op.add_column('log_analyses', sa.Column('is_recurring', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('log_analyses', sa.Column('match_score', sa.Float(), nullable=True))
    op.create_index(op.f('ix_log_analyses_incident_group_id'), 'log_analyses', ['incident_group_id'], unique=False)
    op.create_foreign_key(
        'fk_log_analyses_incident_group_id', 'log_analyses', 'incident_groups',
        ['incident_group_id'], ['id'], ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint('fk_log_analyses_incident_group_id', 'log_analyses', type_='foreignkey')
    op.drop_index(op.f('ix_log_analyses_incident_group_id'), table_name='log_analyses')
    op.drop_column('log_analyses', 'match_score')
    op.drop_column('log_analyses', 'is_recurring')
    op.drop_column('log_analyses', 'incident_group_id')

    op.drop_index(op.f('ix_incident_groups_root_cause_category'), table_name='incident_groups')
    op.drop_index(op.f('ix_incident_groups_fingerprint'), table_name='incident_groups')
    op.drop_index(op.f('ix_incident_groups_id'), table_name='incident_groups')
    op.drop_table('incident_groups')
