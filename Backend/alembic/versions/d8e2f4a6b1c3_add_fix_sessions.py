"""add_fix_sessions

Revision ID: d8e2f4a6b1c3
Revises: a2c4e6f8b0d1
Create Date: 2026-10-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8e2f4a6b1c3'
down_revision: Union[str, None] = 'a2c4e6f8b0d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'fix_sessions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('log_id', sa.Integer(), nullable=False),
        sa.Column('analysis_id', sa.Integer(), nullable=True),
        sa.Column('incident_decision_id', sa.Integer(), nullable=True),
        sa.Column('trigger', sa.String(length=20), nullable=False),
        sa.Column('executor', sa.String(length=50), nullable=False),
        sa.Column('priority', sa.String(length=10), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('gitlab_project', sa.String(length=255), nullable=True),
        sa.Column('base_branch', sa.String(length=255), nullable=True),
        sa.Column('branch', sa.String(length=255), nullable=True),
        sa.Column('commit_sha', sa.String(length=64), nullable=True),
        sa.Column('merge_request_url', sa.String(length=1024), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('root_cause_confirmed', sa.Text(), nullable=True),
        sa.Column('files_changed', sa.Text(), nullable=True),
        sa.Column('tests_summary', sa.Text(), nullable=True),
        sa.Column('ai_hypothesis', sa.Text(), nullable=True),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['log_id'], ['logs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['analysis_id'], ['log_analyses.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['incident_decision_id'], ['incident_decisions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_fix_sessions_id'), 'fix_sessions', ['id'], unique=False)
    op.create_index(op.f('ix_fix_sessions_log_id'), 'fix_sessions', ['log_id'], unique=False)
    op.create_index(op.f('ix_fix_sessions_incident_decision_id'), 'fix_sessions', ['incident_decision_id'], unique=False)
    op.create_index(op.f('ix_fix_sessions_status'), 'fix_sessions', ['status'], unique=False)

    op.create_table(
        'fix_session_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['fix_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_fix_session_events_id'), 'fix_session_events', ['id'], unique=False)
    op.create_index(op.f('ix_fix_session_events_session_id'), 'fix_session_events', ['session_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_fix_session_events_session_id'), table_name='fix_session_events')
    op.drop_index(op.f('ix_fix_session_events_id'), table_name='fix_session_events')
    op.drop_table('fix_session_events')
    op.drop_index(op.f('ix_fix_sessions_status'), table_name='fix_sessions')
    op.drop_index(op.f('ix_fix_sessions_incident_decision_id'), table_name='fix_sessions')
    op.drop_index(op.f('ix_fix_sessions_log_id'), table_name='fix_sessions')
    op.drop_index(op.f('ix_fix_sessions_id'), table_name='fix_sessions')
    op.drop_table('fix_sessions')
