"""Database engine, session factory, declarative base, and light schema repair."""
import logging
from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

logger = logging.getLogger("FiQO.db")
settings = get_settings()

_is_sqlite = settings.database_url.startswith("sqlite")

# SQLite needs a special flag for use across FastAPI's threadpool. Pooling
# options only apply to real server databases.
if _is_sqlite:
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
else:
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,       # drops dead connections instead of erroring
        pool_recycle=1800,        # sidesteps proxy/db idle timeouts
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db() -> Generator:
    """FastAPI dependency that yields a DB session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Columns added after the first release. `create_all` only creates *missing
# tables*, never missing columns, so upgrading an existing database used to
# crash with "no such column". This closes that gap without pulling in Alembic.
# For anything more involved than adding a nullable/defaulted column, use a
# real migration tool.
#
# Each entry maps a column to its DDL per dialect. SQLite has no BOOLEAN type
# and stores 0/1 in an INTEGER; Postgres has a real BOOLEAN and rejects the
# integer default. One shared string cannot satisfy both, so the type is chosen
# per backend rather than hoping the database coerces it.
_ADDITIVE_COLUMNS: dict[str, dict[str, dict[str, str]]] = {
    "users": {
        "token_version": {
            "sqlite": "INTEGER NOT NULL DEFAULT 0",
            "default": "INTEGER NOT NULL DEFAULT 0",
        },
        # Existing accounts are grandfathered in as verified. Backfilling them
        # to false would lock out every current user the moment verification is
        # switched on, which is a self-inflicted outage, not a security win.
        "is_verified": {
            "sqlite": "BOOLEAN NOT NULL DEFAULT 1",
            "default": "BOOLEAN NOT NULL DEFAULT TRUE",
        },
    },
}


def _apply_additive_columns() -> None:
    dialect = engine.dialect.name  # "sqlite" | "postgresql" | ...
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    for table, columns in _ADDITIVE_COLUMNS.items():
        if table not in existing_tables:
            continue
        present = {c["name"] for c in inspector.get_columns(table)}
        for column, ddl_by_dialect in columns.items():
            if column in present:
                continue
            ddl = ddl_by_dialect.get(dialect, ddl_by_dialect["default"])
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
            logger.info("Schema update: added %s.%s", table, column)


def init_db() -> None:
    """Create tables and patch in additive columns. Safe to call repeatedly."""
    # Import models so they are registered on the metadata before create_all.
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _apply_additive_columns()

    # Logged loudly because "which database am I actually on?" is the first
    # question when accounts go missing after a deploy, and the answer is not
    # visible from the outside.
    if _is_sqlite:
        logger.warning(
            "Using SQLITE (%s). On a container host this file is wiped on every "
            "restart or deploy, taking all user accounts with it. Set DATABASE_URL "
            "to a managed Postgres instance for anything real.",
            engine.url.database,
        )
    else:
        logger.info(
            "Database ready: %s at %s", engine.dialect.name, engine.url.host
        )
