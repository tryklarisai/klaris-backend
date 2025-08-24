"""drop business context tables

Revision ID: 20250822_0012_drop_business_context
Revises: 20250821_0011_add_chat_threads
Create Date: 2025-08-22
"""

from typing import Sequence, Union
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '20250822_0012_drop_business_context'
down_revision: Union[str, None] = '20250821_0011_add_chat_threads'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop index if exists, then tables (be tolerant if some do not exist)
    op.execute("DROP INDEX IF EXISTS ux_context_version_per_tenant")
    op.execute("DROP TABLE IF EXISTS context_reviews CASCADE")
    op.execute("DROP TABLE IF EXISTS business_context_canonicals CASCADE")
    op.execute("DROP TABLE IF EXISTS term_mappings CASCADE")
    op.execute("DROP TABLE IF EXISTS business_terms CASCADE")
    op.execute("DROP TABLE IF EXISTS context_chunks CASCADE")
    op.execute("DROP TABLE IF EXISTS context_sources CASCADE")


def downgrade() -> None:
    # No-op: removing feature permanently
    pass




