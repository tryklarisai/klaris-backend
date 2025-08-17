"""
Add vector index tables for pgvector-backed card storage.

Revision ID: 20250814_0009_add_vector_index_tables
Revises: 20250814_0008_add_business_context
Create Date: 2025-08-14
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '20250814_0009_add_vector_index_tables'
down_revision: Union[str, None] = '20250814_0008_add_business_context'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Cards table
    op.create_table(
        'vector_cards',
        sa.Column('card_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('key_kind', sa.String(length=32), nullable=False),  # entity|field|relationship
        sa.Column('key_hash', sa.String(length=128), nullable=False),
        sa.Column('card_text', sa.Text(), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('embedding', postgresql.ARRAY(sa.Float()), nullable=False),  # stored as float[] for portability
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('card_id')
    )
    # Idempotency unique key per kind
    op.create_index('ux_vector_cards_key', 'vector_cards', ['tenant_id', 'key_kind', 'key_hash'], unique=True)


def downgrade() -> None:
    op.drop_index('ux_vector_cards_key', table_name='vector_cards')
    op.drop_table('vector_cards')


