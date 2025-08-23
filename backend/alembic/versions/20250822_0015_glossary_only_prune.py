"""prune BCL to glossary-only: drop unused tables

Revision ID: 20250822_0015_glossary_only_prune
Revises: 20250822_0014_add_bcl_mapping_proposals
Create Date: 2025-08-22
"""

from typing import Sequence, Union
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '20250822_0015_glossary_only_prune'
down_revision: Union[str, None] = '20250822_0014_add_bcl_mapping_proposals'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop indexes first where necessary, then tables; ignore errors if not present
    op.execute("DROP INDEX IF EXISTS ix_bcl_chunks_embedding")
    op.execute("DROP INDEX IF EXISTS ix_bcl_chunks_fts")
    op.execute("DROP INDEX IF EXISTS ix_bcl_chunks_doc")
    op.execute("DROP INDEX IF EXISTS ix_bcl_chunks_tenant")
    op.execute("DROP INDEX IF EXISTS ix_bcl_term_mappings_term")
    op.execute("DROP INDEX IF EXISTS ix_bcl_term_mappings_tenant")
    op.execute("DROP INDEX IF EXISTS ix_bcl_term_evidence_term")
    op.execute("DROP INDEX IF EXISTS ix_bcl_term_evidence_chunk")
    op.execute("DROP INDEX IF EXISTS ux_bcl_term_alias_norm")
    op.execute("DROP INDEX IF EXISTS ix_bcl_mapping_proposals_tenant")
    op.execute("DROP INDEX IF EXISTS ix_bcl_mapping_proposals_term")

    op.execute("DROP TABLE IF EXISTS bcl_term_evidence CASCADE")
    op.execute("DROP TABLE IF EXISTS bcl_term_mappings CASCADE")
    op.execute("DROP TABLE IF EXISTS bcl_term_aliases CASCADE")
    op.execute("DROP TABLE IF EXISTS bcl_chunks CASCADE")
    op.execute("DROP TABLE IF EXISTS bcl_documents CASCADE")
    op.execute("DROP TABLE IF EXISTS bcl_mapping_proposals CASCADE")


def downgrade() -> None:
    # No-op; prior migrations can recreate the dropped tables if needed
    pass


