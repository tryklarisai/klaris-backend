"""
add usage_events table for LLM/embeddings usage tracking

Revision ID: 20250823_0013_add_usage_events
Revises: 20250822_0012_drop_business_context
Create Date: 2025-08-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '20250823_0013_add_usage_events'
down_revision = '20250822_0012_drop_business_context'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
    op.create_table(
        'usage_events',
        sa.Column('event_id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('provider', sa.Text(), nullable=False),
        sa.Column('model', sa.Text(), nullable=True),
        sa.Column('operation', sa.Text(), nullable=False),  # chat | embedding
        sa.Column('category', sa.Text(), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('total_tokens', sa.Integer(), nullable=True),
        sa.Column('request_id', sa.Text(), nullable=True),
        sa.Column('thread_id', sa.Text(), nullable=True),
        sa.Column('route', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('retry_attempt', sa.Integer(), nullable=True),
        sa.Column('cache_hit', sa.Boolean(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index('ix_usage_events_tenant_time', 'usage_events', ['tenant_id', 'occurred_at'])
    op.create_index('ix_usage_events_tenant_category_time', 'usage_events', ['tenant_id', 'category', 'occurred_at'])
    # Intentionally no unique constraint for dedupe; we want every attempt logged


def downgrade() -> None:
    op.drop_index('ix_usage_events_tenant_category_time', table_name='usage_events')
    op.drop_index('ix_usage_events_tenant_time', table_name='usage_events')
    op.drop_table('usage_events')


