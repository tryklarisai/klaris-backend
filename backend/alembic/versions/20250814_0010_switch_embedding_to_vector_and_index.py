"""
Create vector index tables with pgvector and IVFFLAT index (merged migration).

Revision ID: 20250814_0010_switch_embedding_to_vector_and_index
Revises: 20250814_0008_add_business_context
Create Date: 2025-08-14
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
import os


# revision identifiers, used by Alembic.
revision: str = '20250814_0010_switch_embedding_to_vector_and_index'
down_revision: Union[str, None] = '20250814_0008_add_business_context'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure required extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # Determine embedding dimension and IVFFLAT lists from env
    try:
        dim = int(os.getenv('VECTOR_DIM', '1536'))
    except Exception:
        dim = 1536
    try:
        lists = int(os.getenv('VECTOR_IVFFLAT_LISTS', '100'))
    except Exception:
        lists = 100

    # Create table
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS vector_cards (
            card_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            key_kind VARCHAR(32) NOT NULL,
            key_hash VARCHAR(128) NOT NULL,
            card_text TEXT NOT NULL,
            metadata JSONB NOT NULL,
            embedding vector({dim}) NOT NULL,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL
        )
        """
    )

    # Unique idempotency key
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_vector_cards_key ON vector_cards (tenant_id, key_kind, key_hash)")

    # IVFFLAT index for cosine distance
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_vector_cards_embedding ON vector_cards USING ivfflat (embedding vector_cosine_ops) WITH (lists = {lists})")


def downgrade() -> None:
    # Drop index and table
    op.execute("DROP INDEX IF EXISTS ix_vector_cards_embedding")
    op.execute("DROP INDEX IF EXISTS ux_vector_cards_key")
    op.execute("DROP TABLE IF EXISTS vector_cards")


