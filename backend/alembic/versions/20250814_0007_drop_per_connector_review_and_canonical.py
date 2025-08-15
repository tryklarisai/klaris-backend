"""drop per-connector schema_reviews and canonical_schemas tables

Revision ID: 20250814_0007_drop_per_connector_review_and_canonical
Revises: 20250814_0006_add_dataset_and_global_canonical
Create Date: 2025-08-14
"""

from alembic import op

revision = '20250814_0007_drop_per_connector_review_and_canonical'
down_revision = '20250814_0006_add_dataset_and_global_canonical'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table('canonical_schemas')
    op.drop_table('schema_reviews')


def downgrade() -> None:
    # Not implementing a full recreation here to keep history simple
    pass


