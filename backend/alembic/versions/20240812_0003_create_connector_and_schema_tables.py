"""
20240812_0003_create_connector_and_schema_tables.py
Alembic migration: creates connectors and schemas tables
"""
from alembic import op
import sqlalchemy as sa
import sqlalchemy.dialects.postgresql as pg
from datetime import datetime

# revision identifiers, used by Alembic.
revision = '20240812_0003_create_connector_and_schema_tables'
down_revision = '20240811_0002_create_user_table'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'connectors',
        sa.Column('connector_id', pg.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('tenant_id', pg.UUID(as_uuid=True), sa.ForeignKey('tenants.tenant_id', ondelete='CASCADE'), nullable=False),
        sa.Column('type', sa.String(length=32), nullable=False),
        sa.Column('config', pg.JSONB, nullable=False),
        sa.Column('status', sa.Enum('active', 'failed', name='connectorstatus'), nullable=False, server_default='failed'),
        sa.Column('last_schema_fetch', sa.DateTime(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, default=datetime.utcnow),
        sa.Column('updated_at', sa.DateTime(), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow),
    )
    op.create_table(
        'schemas',
        sa.Column('schema_id', pg.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('connector_id', pg.UUID(as_uuid=True), sa.ForeignKey('connectors.connector_id', ondelete='CASCADE'), nullable=False),
        sa.Column('tenant_id', pg.UUID(as_uuid=True), sa.ForeignKey('tenants.tenant_id', ondelete='CASCADE'), nullable=False),
        sa.Column('raw_schema', pg.JSONB, nullable=False),
        sa.Column('fetched_at', sa.DateTime(), nullable=False, default=datetime.utcnow),
    )
    # Create Enum Type for ConnectorStatus so downgrade can drop it

def downgrade():
    op.drop_table('schemas')
    op.drop_table('connectors')
    op.execute("DROP TYPE IF EXISTS connectorstatus;")
