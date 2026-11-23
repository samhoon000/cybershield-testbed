"""add simulation_sessions table

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-23

"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'simulation_sessions',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('incident_id', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('target_app', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('unlocked_at', sa.DateTime(), nullable=True),
        sa.Column('terminated_at', sa.DateTime(), nullable=True),
        sa.Column('client_ip', sa.String(length=45), nullable=True),
        sa.Column('notes', sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('simulation_sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_simulation_sessions_incident_id'), ['incident_id'], unique=True)
        batch_op.create_index(batch_op.f('ix_simulation_sessions_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_simulation_sessions_expires_at'), ['expires_at'], unique=False)
        batch_op.create_index('ix_simulation_sessions_status_exp', ['status', 'expires_at'], unique=False)


def downgrade():
    with op.batch_alter_table('simulation_sessions', schema=None) as batch_op:
        batch_op.drop_index('ix_simulation_sessions_status_exp')
        batch_op.drop_index(batch_op.f('ix_simulation_sessions_expires_at'))
        batch_op.drop_index(batch_op.f('ix_simulation_sessions_status'))
        batch_op.drop_index(batch_op.f('ix_simulation_sessions_incident_id'))
    op.drop_table('simulation_sessions')
