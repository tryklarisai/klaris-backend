"""
Add unique constraint on connector name per tenant
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250821_0012_add_unique_constraint_connector_name_per_tenant'
down_revision = '20250820_0011_add_name_to_connector'
branch_labels = None
depends_on = None

def upgrade():
    # Add unique constraint on (tenant_id, name) where name is not null
    op.create_unique_constraint(
        'uq_connector_name_per_tenant',
        'connectors', 
        ['tenant_id', 'name'],
        # SQLite doesn't support partial unique constraints, but PostgreSQL does
        # For PostgreSQL, we want: WHERE name IS NOT NULL
        postgresql_where=sa.text('name IS NOT NULL')
    )

def downgrade():
    op.drop_constraint('uq_connector_name_per_tenant', 'connectors', type_='unique')