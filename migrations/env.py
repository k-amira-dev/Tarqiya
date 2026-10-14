"""Alembic environment: uses DATABASE_URL and the PromoFlow model metadata.

WHAT IS ALEMBIC? (for beginners)
Alembic is the tool that changes the database's STRUCTURE over time. Each change is a numbered file in
migrations/versions/. `alembic upgrade head` applies every change that has not been applied yet, so any database can be
brought up to date, and every developer's database ends up identical. THIS file only tells Alembic how to connect to
the database and where to find the table definitions; you rarely need to edit it.
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

# Importing the models registers every table on Base.metadata, which is what Alembic compares against the real
# database when it creates a new migration.
import promoflow.db.models  # noqa: F401  (registers all tables)
from promoflow.config import DATABASE_URL
from promoflow.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The description of the tables the code expects. `alembic revision --autogenerate` compares it with the database to
# write the migration for you.
target_metadata = Base.metadata


# Tell Alembic which database objects to look at. It must IGNORE the tables LangGraph creates for its checkpoints,
# otherwise autogenerate would try to drop them.
def include_object(obj, name, type_, reflected, compare_to):
    # LangGraph creates and manages its own checkpoint tables; never touch them.
    if type_ == "table" and name.startswith("checkpoint"):
        return False
    return True


# Offline mode: do not connect, just print the SQL (`alembic upgrade head --sql`). Useful to review exactly what a
# migration will do.
def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it (alembic upgrade head --sql)."""
    context.configure(
        url=DATABASE_URL, target_metadata=target_metadata, literal_binds=True,
        dialect_opts={"paramstyle": "named"}, include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


# Normal mode: connect to the database in DATABASE_URL and run the migrations. NullPool = do not keep connections
# open afterwards.
def run_migrations_online() -> None:
    connectable = create_engine(DATABASE_URL, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, include_object=include_object)
        with context.begin_transaction():
            context.run_migrations()


# Alembic tells us which mode the command was started in.
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
