"""
Add metadata json field to connector
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20240813_0004_add_metadata_to_connector'
down_revision = '20240812_0003_create_connector_and_schema_tables'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('connectors', sa.Column('connector_metadata', sa.dialects.postgresql.JSONB(), nullable=True))

def downgrade():
    op.drop_column('connectors', 'connector_metadata')
