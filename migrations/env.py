"""Alembic environment: uses DATABASE_URL and the PromoFlow model metadata."""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

import promoflow.db.models  # noqa: F401  (registers all tables)
from promoflow.config import DATABASE_URL
from promoflow.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to):
    # LangGraph creates and manages its own checkpoint tables; never touch them.
    if type_ == "table" and name.startswith("checkpoint"):
        return False
    return True


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it (alembic upgrade head --sql)."""
    context.configure(
        url=DATABASE_URL, target_metadata=target_metadata, literal_binds=True,
        dialect_opts={"paramstyle": "named"}, include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(DATABASE_URL, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, include_object=include_object)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
