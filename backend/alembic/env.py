"""Alembic env.py — async, shared Base, pgvector pre-import.

D-12: migrations run manually (`alembic upgrade head`); never auto-run from lifespan.
D-17: DATABASE_URL is read via `from app.core.settings import settings` — no os.getenv.
P-06: every model module is imported below so its tables register on Base.metadata.
P-07: pgvector.sqlalchemy is imported BEFORE any sqlalchemy async import.
"""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

# P-07: pgvector type registration must precede engine creation.
import pgvector.sqlalchemy  # noqa: F401

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# D-17: pull DATABASE_URL via settings (no os.getenv).
from app.core.settings import settings

# P-06: import every model module so its tables register on Base.metadata BEFORE
# target_metadata is read. Without these imports, autogenerate produces an empty diff.
from app.db.base import Base
from app.models import tool_call, trip, user  # noqa: F401
from rag import models as rag_models  # noqa: F401  — Chunk

config = context.config

# Inject runtime DSN (alembic.ini sqlalchemy.url is empty).
config.set_main_option("sqlalchemy.url", str(settings.database_url))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
