"""
add module column to usage_events

Revision ID: 20250823_0014_add_module_to_usage_events
Revises: 20250823_0013_add_usage_events
Create Date: 2025-08-23
"""

from alembic import op
import sqlalchemy as sa


revision = '20250823_0014_add_module_to_usage_events'
down_revision = '20250823_0013_add_usage_events'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('usage_events', sa.Column('module', sa.Text(), nullable=True))
    op.create_index('ix_usage_events_tenant_module_time', 'usage_events', ['tenant_id', 'module', 'occurred_at'])


def downgrade() -> None:
    op.drop_index('ix_usage_events_tenant_module_time', table_name='usage_events')
    op.drop_column('usage_events', 'module')


