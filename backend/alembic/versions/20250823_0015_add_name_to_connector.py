"""
Add name field to connector table for user-defined connector names
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250823_0015_add_name_to_connector'
down_revision = '20250823_0014_add_module_to_usage_events'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('connectors', sa.Column('name', sa.String(255), nullable=True))

def downgrade():
    op.drop_column('connectors', 'name')