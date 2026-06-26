"""initial

Revision ID: 0001
Revises: 
Create Date: 2026-06-07 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    # create log_files table
    op.create_table(
        'log_files',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('file_name', sa.String(length=255), nullable=False),
        sa.Column('file_path', sa.String(length=1024), nullable=False),
        sa.Column('service_name', sa.String(length=100), nullable=False),
        sa.Column('last_processed_position', sa.BigInteger(), nullable=False),
        sa.Column('last_processed_time', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_log_files_file_path'), 'log_files', ['file_path'], unique=True)
    op.create_index(op.f('ix_log_files_id'), 'log_files', ['id'], unique=False)

    # create logs table
    op.create_table(
        'logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('service_name', sa.String(length=100), nullable=False),
        sa.Column('log_level', sa.String(length=50), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('stacktrace', sa.Text(), nullable=True),
        sa.Column('file_name', sa.String(length=255), nullable=False),
        sa.Column('file_path', sa.String(length=1024), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_logs_id'), 'logs', ['id'], unique=False)
    op.create_index(op.f('ix_logs_log_level'), 'logs', ['log_level'], unique=False)
    op.create_index(op.f('ix_logs_service_name'), 'logs', ['service_name'], unique=False)
    op.create_index(op.f('ix_logs_timestamp'), 'logs', ['timestamp'], unique=False)

def downgrade() -> None:
    op.drop_index(op.f('ix_logs_timestamp'), table_name='logs')
    op.drop_index(op.f('ix_logs_service_name'), table_name='logs')
    op.drop_index(op.f('ix_logs_log_level'), table_name='logs')
    op.drop_index(op.f('ix_logs_id'), table_name='logs')
    op.drop_table('logs')
    op.drop_index(op.f('ix_log_files_id'), table_name='log_files')
    op.drop_index(op.f('ix_log_files_file_path'), table_name='log_files')
    op.drop_table('log_files')
