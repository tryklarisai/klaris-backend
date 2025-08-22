"""create business context layer (BCL) tables

Revision ID: 20250822_0013_create_bcl_schema
Revises: 20250822_0012_drop_business_context
Create Date: 2025-08-22
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
import os


# revision identifiers, used by Alembic.
revision: str = '20250822_0013_create_bcl_schema'
down_revision: Union[str, None] = '20250822_0012_drop_business_context'
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

    # Documents (sources)
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS bcl_documents (
            document_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
            uri TEXT NOT NULL,
            title TEXT,
            mime_type VARCHAR(128),
            kind VARCHAR(16) NOT NULL,
            status VARCHAR(16) NOT NULL,
            error_message TEXT,
            source_meta JSONB,
            created_at TIMESTAMP NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_bcl_documents_tenant ON bcl_documents (tenant_id)")

    # Content chunks with vector embeddings and provenance metadata
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS bcl_chunks (
            chunk_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
            document_id UUID NOT NULL REFERENCES bcl_documents(document_id) ON DELETE CASCADE,
            text TEXT NOT NULL,
            embedding vector({dim}) NOT NULL,
            metadata JSONB,
            created_at TIMESTAMP NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_bcl_chunks_tenant ON bcl_chunks (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_bcl_chunks_doc ON bcl_chunks (document_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_bcl_chunks_fts ON bcl_chunks USING GIN (to_tsvector('english', text))")
    op.execute(
        f"CREATE INDEX IF NOT EXISTS ix_bcl_chunks_embedding ON bcl_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = {lists})"
    )

    # Glossary terms (with optional embedding)
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS bcl_terms (
            term_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
            term VARCHAR(256) NOT NULL,
            normalized_term VARCHAR(256) NOT NULL,
            description TEXT,
            embedding vector({dim}),
            examples JSONB,
            source_meta JSONB,
            created_at TIMESTAMP NOT NULL
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_bcl_terms_norm ON bcl_terms (tenant_id, normalized_term)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_bcl_terms_fts ON bcl_terms USING GIN (to_tsvector('english', coalesce(term,'') || ' ' || coalesce(description,'')))"
    )
    op.execute(
        f"CREATE INDEX IF NOT EXISTS ix_bcl_terms_embedding ON bcl_terms USING ivfflat (embedding vector_cosine_ops) WITH (lists = {lists})"
    )

    # Term aliases
    op.create_table(
        'bcl_term_aliases',
        sa.Column('alias_id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('tenant_id', sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.tenant_id', ondelete='CASCADE'), nullable=False),
        sa.Column('term_id', sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey('bcl_terms.term_id', ondelete='CASCADE'), nullable=False),
        sa.Column('alias', sa.String(length=256), nullable=False),
        sa.Column('normalized_alias', sa.String(length=256), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_bcl_term_alias_norm ON bcl_term_aliases (tenant_id, normalized_alias)")

    # Term mappings to canonical schema targets
    op.create_table(
        'bcl_term_mappings',
        sa.Column('mapping_id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('tenant_id', sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.tenant_id', ondelete='CASCADE'), nullable=False),
        sa.Column('term_id', sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey('bcl_terms.term_id', ondelete='CASCADE'), nullable=False),
        sa.Column('target_kind', sa.String(length=16), nullable=False),  # table | column | expression | filter
        sa.Column('entity_name', sa.String(length=256), nullable=True),
        sa.Column('field_name', sa.String(length=256), nullable=True),
        sa.Column('expression', sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('filter', sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('rationale', sa.Text(), nullable=True),
        sa.Column('confidence', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_bcl_term_mappings_tenant ON bcl_term_mappings (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_bcl_term_mappings_term ON bcl_term_mappings (term_id)")

    # Evidence linking terms to chunks (provenance)
    op.create_table(
        'bcl_term_evidence',
        sa.Column('evidence_id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('tenant_id', sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.tenant_id', ondelete='CASCADE'), nullable=False),
        sa.Column('term_id', sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey('bcl_terms.term_id', ondelete='CASCADE'), nullable=False),
        sa.Column('chunk_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),  # references bcl_chunks.chunk_id
        sa.Column('score', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    # FK to chunks (created via raw SQL table); add explicit constraint
    op.create_foreign_key(
        'fk_bcl_evidence_chunk',
        'bcl_term_evidence', 'bcl_chunks', ['chunk_id'], ['chunk_id'], ondelete='CASCADE'
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_bcl_term_evidence_term ON bcl_term_evidence (term_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_bcl_term_evidence_chunk ON bcl_term_evidence (chunk_id)")


def downgrade() -> None:
    # Drop evidence and mappings/aliases
    op.execute("DROP INDEX IF EXISTS ix_bcl_term_evidence_chunk")
    op.execute("DROP INDEX IF EXISTS ix_bcl_term_evidence_term")
    op.drop_constraint('fk_bcl_evidence_chunk', 'bcl_term_evidence', type_='foreignkey')
    op.drop_table('bcl_term_evidence')

    op.execute("DROP INDEX IF EXISTS ix_bcl_term_mappings_term")
    op.execute("DROP INDEX IF EXISTS ix_bcl_term_mappings_tenant")
    op.drop_table('bcl_term_mappings')

    op.execute("DROP INDEX IF EXISTS ux_bcl_term_alias_norm")
    op.drop_table('bcl_term_aliases')

    # Drop terms
    op.execute("DROP INDEX IF EXISTS ix_bcl_terms_embedding")
    op.execute("DROP INDEX IF EXISTS ix_bcl_terms_fts")
    op.execute("DROP INDEX IF EXISTS ux_bcl_terms_norm")
    op.execute("DROP TABLE IF EXISTS bcl_terms")

    # Drop chunks
    op.execute("DROP INDEX IF EXISTS ix_bcl_chunks_embedding")
    op.execute("DROP INDEX IF EXISTS ix_bcl_chunks_fts")
    op.execute("DROP INDEX IF EXISTS ix_bcl_chunks_doc")
    op.execute("DROP INDEX IF EXISTS ix_bcl_chunks_tenant")
    op.execute("DROP TABLE IF EXISTS bcl_chunks")

    # Drop documents
    op.execute("DROP INDEX IF EXISTS ix_bcl_documents_tenant")
    op.execute("DROP TABLE IF EXISTS bcl_documents")



