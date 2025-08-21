"""
Add chat_threads table for persistent chat thread titles.

Revision ID: 20250821_0011_add_chat_threads
Revises: 20250814_0010_switch_embedding_to_vector_and_index
Create Date: 2025-08-21
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20250821_0011_add_chat_threads'
down_revision: Union[str, None] = '20250814_0010_switch_embedding_to_vector_and_index'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'chat_threads',
        sa.Column('thread_id', sa.String(length=32), primary_key=True, nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.tenant_id'], ondelete='CASCADE'),
    )
    # Helpful index for listing threads by tenant and recency
    op.create_index('ix_chat_threads_tenant_updated_at', 'chat_threads', ['tenant_id', 'updated_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_chat_threads_tenant_updated_at', table_name='chat_threads')
    op.drop_table('chat_threads')
