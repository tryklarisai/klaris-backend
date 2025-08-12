"""
Alembic environment configuration for migrations.
Handles database URL securely via environment variables.
"""
from logging.config import fileConfig
import os
from sqlalchemy import engine_from_config, pool
from alembic import context
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from models.tenant import Base  # Import all model Bases here for 'autogenerate'
from models.user import User

# Alembic Config object
config = context.config

# Interpret the config file for Python logging.
fileConfig(config.config_file_name)

target_metadata = Base.metadata

def get_url():
    return os.getenv("DATABASE_URL", "postgresql://postgres:postgres@db:5432/postgres")

def run_migrations_offline():
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(
        {**config.get_section(config.config_ini_section), "sqlalchemy.url": get_url()},
        prefix="sqlalchemy."
        , poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
