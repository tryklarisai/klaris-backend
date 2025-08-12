"""
2024-08-11: Create user table with FK to tenant and unique email-per-tenant
"""
revision = '20240811_0002_create_user_table'
down_revision = '20240811_0001_create_tenant_table'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

def upgrade():
    op.create_table(
        'users',
        sa.Column('user_id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.tenant_id', ondelete="CASCADE"), nullable=False),
        sa.Column('name', sa.String(80), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('hashed_password', sa.String(128), nullable=False),
        sa.Column('is_root', sa.Boolean, nullable=False, default=False),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('tenant_id', 'email', name='uq_tenant_email'),
    )

def downgrade():
    op.drop_table('users')
