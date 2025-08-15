"""add dataset_reviews and global_canonical_schemas tables

Revision ID: 20250814_0006_add_dataset_and_global_canonical
Revises: 20250814_0005_add_schema_review_and_canonical
Create Date: 2025-08-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20250814_0006_add_dataset_and_global_canonical'
down_revision = '20250814_0005_add_schema_review_and_canonical'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'dataset_reviews',
        sa.Column('review_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
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
    op.create_index('ix_dataset_reviews_tenant_created_at', 'dataset_reviews', ['tenant_id', 'created_at'], unique=False)

    op.create_table(
        'global_canonical_schemas',
        sa.Column('global_canonical_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('base_schema_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('canonical_graph', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('approved_by_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('global_canonical_id')
    )
    op.create_index('ux_global_canonical_version_per_tenant', 'global_canonical_schemas', ['tenant_id', 'version'], unique=True)


def downgrade() -> None:
    op.drop_index('ux_global_canonical_version_per_tenant', table_name='global_canonical_schemas')
    op.drop_table('global_canonical_schemas')
    op.drop_index('ix_dataset_reviews_tenant_created_at', table_name='dataset_reviews')
    op.drop_table('dataset_reviews')


