"""add bcl mapping proposals table

Revision ID: 20250822_0014_add_bcl_mapping_proposals
Revises: 20250822_0013_create_bcl_schema
Create Date: 2025-08-22
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20250822_0014_add_bcl_mapping_proposals'
down_revision: Union[str, None] = '20250822_0013_create_bcl_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'bcl_mapping_proposals',
        sa.Column('proposal_id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('tenant_id', sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.tenant_id', ondelete='CASCADE'), nullable=False),
        sa.Column('term_id', sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey('bcl_terms.term_id', ondelete='CASCADE'), nullable=False),
        sa.Column('target_kind', sa.String(length=16), nullable=False),
        sa.Column('entity_name', sa.String(length=256), nullable=True),
        sa.Column('field_name', sa.String(length=256), nullable=True),
        sa.Column('expression', sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('filter', sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('rationale', sa.Text(), nullable=True),
        sa.Column('confidence', sa.Integer(), nullable=True),
        sa.Column('evidence', sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_bcl_mapping_proposals_tenant ON bcl_mapping_proposals (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_bcl_mapping_proposals_term ON bcl_mapping_proposals (term_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_bcl_mapping_proposals_term")
    op.execute("DROP INDEX IF EXISTS ix_bcl_mapping_proposals_tenant")
    op.drop_table('bcl_mapping_proposals')


