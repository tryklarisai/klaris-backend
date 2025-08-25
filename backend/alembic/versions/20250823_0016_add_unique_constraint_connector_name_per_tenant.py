"""
Add unique constraint on connector name per tenant
"""
from alembic import op
import sqlalchemy as sa

# Revision identifiers, used by Alembic
revision = '20250823_0016_add_unique_constraint_connector_name_per_tenant'
down_revision = '20250823_0015_add_name_to_connector'
branch_labels = None
depends_on = None


def upgrade():
    # Create a partial unique index instead of unique constraint
    op.create_index(
        'uq_connector_name_per_tenant',
        'connectors',
        ['tenant_id', 'name'],
        unique=True,
        postgresql_where=sa.text('name IS NOT NULL')
    )


def downgrade():
    op.drop_index('uq_connector_name_per_tenant', table_name='connectors')
