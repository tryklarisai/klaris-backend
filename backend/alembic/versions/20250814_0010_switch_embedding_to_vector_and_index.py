"""
Switch embedding column to pgvector 'vector' type and add IVFFLAT index.

Revision ID: 20250814_0010_switch_embedding_to_vector_and_index
Revises: 20250814_0009_add_vector_index_tables
Create Date: 2025-08-14
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
import os


# revision identifiers, used by Alembic.
revision: str = '20250814_0010_switch_embedding_to_vector_and_index'
down_revision: Union[str, None] = '20250814_0009_add_vector_index_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # Drop existing embedding column and re-add as vector with dimension
    try:
        dim = int(os.getenv('VECTOR_DIM', '1536'))
    except Exception:
        dim = 1536
    op.execute("ALTER TABLE vector_cards DROP COLUMN IF EXISTS embedding")
    op.execute(f"ALTER TABLE vector_cards ADD COLUMN embedding vector({dim}) NOT NULL")
    # Create IVFFLAT index for cosine distance
    try:
        lists = int(os.getenv('VECTOR_IVFFLAT_LISTS', '100'))
    except Exception:
        lists = 100
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_vector_cards_embedding ON vector_cards USING ivfflat (embedding vector_cosine_ops) WITH (lists = {lists})")


def downgrade() -> None:
    # Drop index and revert to float[] for portability
    op.execute("DROP INDEX IF EXISTS ix_vector_cards_embedding")
    op.execute("ALTER TABLE vector_cards DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE vector_cards ADD COLUMN embedding double precision[] NOT NULL")


