"""add schema_reviews and canonical_schemas tables

Revision ID: 20250814_0005
Revises: 20240813_0004
Create Date: 2025-08-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20250814_0005_add_schema_review_and_canonical'
down_revision = '20240813_0004_add_metadata_to_connector'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'schema_reviews',
        sa.Column('review_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('connector_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_schema_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('provider', sa.String(length=64), nullable=False),
        sa.Column('model', sa.String(length=128), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('input_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('suggestions', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('token_usage', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_by_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('review_id')
    )
    op.create_index('ix_schema_reviews_tenant_connector_created_at', 'schema_reviews', ['tenant_id', 'connector_id', 'created_at'], unique=False)

    op.create_table(
        'canonical_schemas',
        sa.Column('canonical_schema_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('connector_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('base_schema_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('canonical_schema', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('approved_by_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('canonical_schema_id')
    )
    op.create_index('ux_canonical_version_per_connector', 'canonical_schemas', ['tenant_id', 'connector_id', 'version'], unique=True)


def downgrade() -> None:
    op.drop_index('ux_canonical_version_per_connector', table_name='canonical_schemas')
    op.drop_table('canonical_schemas')
    op.drop_index('ix_schema_reviews_tenant_connector_created_at', table_name='schema_reviews')
    op.drop_table('schema_reviews')


