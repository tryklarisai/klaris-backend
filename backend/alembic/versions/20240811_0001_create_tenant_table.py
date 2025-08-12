"""
Create tenants table

Revision ID: 20240811_0001_create_tenant_table
Revises: 
Create Date: 2025-08-11
"""
revision = '20240811_0001_create_tenant_table'
down_revision = None
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
import sqlalchemy.dialects.postgresql as pg

def upgrade():
    op.create_table(
        "tenants",
        sa.Column("tenant_id", pg.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("plan", sa.String(length=32), nullable=False),
        sa.Column("credit_balance", sa.Integer, nullable=False, server_default="0"),
        sa.Column("settings", pg.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )

def downgrade():
    op.drop_table("tenants")
