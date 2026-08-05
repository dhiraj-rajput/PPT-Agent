"""
utils/mysql_client.py
---------------------
MySQL connection layer — SQLAlchemy 2.0 async engine + session factory.

Usage:
    # Async (FastAPI route / async function):
    from utils.mysql_client import AsyncSessionLocal, get_db_session

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))

    # As a FastAPI dependency:
    @router.get("/me")
    async def me(db: AsyncSession = Depends(get_db_session)):
        ...

    # Sync (background worker / cron job):
    from utils.mysql_client import get_sync_db_session

    with get_sync_db_session() as db:
        result = db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

    # Schema initialisation (called once at startup):
    from utils.mysql_client import init_mysql
    await init_mysql()
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config.settings import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Declarative Base — all SQL models inherit from this
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """SQLAlchemy ORM declarative base shared by all MySQL table models."""
    pass


# ---------------------------------------------------------------------------
# Async Engine & Session Factory
# ---------------------------------------------------------------------------

def _build_async_engine():
    """Build the async SQLAlchemy engine from settings."""
    uri = getattr(settings, "MYSQL_URI", "") or getattr(settings, "mysql_uri", "")
    if not uri:
        logger.warning(
            "[mysql_client] MYSQL_URI not set — MySQL features will be unavailable."
        )
        return None

    pool_size = int(getattr(settings, "MYSQL_POOL_SIZE", 5))
    max_overflow = int(getattr(settings, "MYSQL_MAX_OVERFLOW", 10))
    echo = bool(getattr(settings, "MYSQL_ECHO", False))

    return create_async_engine(
        uri,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,          # Reconnect on stale connections
        pool_recycle=3600,           # Recycle connections every hour
        echo=echo,
    )


def _build_sync_engine():
    """Build a synchronous SQLAlchemy engine (for background workers)."""
    uri = getattr(settings, "MYSQL_URI_SYNC", "") or getattr(settings, "mysql_uri_sync", "")
    if not uri:
        # Fallback: convert async URI to sync if possible
        async_uri = getattr(settings, "MYSQL_URI", "") or getattr(settings, "mysql_uri", "")
        if async_uri:
            uri = async_uri.replace("mysql+asyncmy://", "mysql+pymysql://").replace("mysql+aiomysql://", "mysql+pymysql://")
    if not uri:
        return None


    echo = bool(getattr(settings, "MYSQL_ECHO", False))
    return create_engine(
        uri,
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=echo,
    )


# Module-level engine instances (lazy-initialised)
_async_engine = None
_sync_engine = None
_AsyncSessionLocal = None
_SyncSessionLocal = None


def _get_async_engine():
    global _async_engine
    if _async_engine is None:
        _async_engine = _build_async_engine()
    return _async_engine


def _get_sync_engine():
    global _sync_engine
    if _sync_engine is None:
        _sync_engine = _build_sync_engine()
    return _sync_engine


def _get_async_session_maker():
    global _AsyncSessionLocal
    if _AsyncSessionLocal is None:
        engine = _get_async_engine()
        if engine is None:
            return None
        _AsyncSessionLocal = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _AsyncSessionLocal


def _get_sync_session_maker():
    global _SyncSessionLocal
    if _SyncSessionLocal is None:
        engine = _get_sync_engine()
        if engine is None:
            return None
        _SyncSessionLocal = sessionmaker(
            bind=engine,
            expire_on_commit=False,
        )
    return _SyncSessionLocal


# Public aliases (used as callables by other modules)
def AsyncSessionLocal():
    """Return a new async session context manager."""
    maker = _get_async_session_maker()
    if maker is None:
        raise RuntimeError(
            "MySQL is not configured. Set MYSQL_URI in your .env file."
        )
    return maker()


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI async dependency that yields a MySQL AsyncSession.

    Usage:
        from utils.mysql_client import get_db_session
        from sqlalchemy.ext.asyncio import AsyncSession

        @router.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db_session)):
            result = await db.execute(select(Item))
            return result.scalars().all()
    """
    maker = _get_async_session_maker()
    if maker is None:
        raise RuntimeError("MySQL is not configured. Set MYSQL_URI in .env")

    async with maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@contextmanager
def get_sync_db_session() -> Generator[Session, None, None]:
    """
    Sync context-manager dependency for background workers and cron jobs.

    Usage:
        from utils.mysql_client import get_sync_db_session

        with get_sync_db_session() as db:
            user = db.execute(select(User).where(...)).scalar_one_or_none()
    """
    maker = _get_sync_session_maker()
    if maker is None:
        raise RuntimeError("MySQL is not configured. Set MYSQL_URI_SYNC in .env")

    session = maker()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Schema Initialisation
# ---------------------------------------------------------------------------

async def init_mysql() -> bool:
    """
    Create all MySQL tables defined in Base.metadata (if they don't exist).

    Called once at application startup (from server.py lifespan handler).
    Safe to call multiple times — uses CREATE TABLE IF NOT EXISTS semantics.

    Returns:
        True if tables were initialised successfully, False otherwise.
    """
    engine = _get_async_engine()
    if engine is None:
        logger.warning("[mysql_client] init_mysql() skipped — MYSQL_URI not set.")
        return False

    try:
        import pymysql
        db_name = getattr(settings, "MYSQL_DB", "winbidai")
        host = getattr(settings, "MYSQL_HOST", "localhost")
        port = int(getattr(settings, "MYSQL_PORT", 3306))
        user = getattr(settings, "MYSQL_USER", "root")
        password = getattr(settings, "MYSQL_PASSWORD", "")
        try:
            conn = pymysql.connect(host=host, port=port, user=user, password=password)
            with conn.cursor() as cursor:
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
            conn.close()
        except Exception as e:
            logger.warning(f"[mysql_client] Database creation check warning: {e}")

        # Import all models so they register with Base.metadata
        from models import sql_models  # noqa: F401 — side-effect: registers all models

        def _sync_missing_columns(connection):
            from sqlalchemy import inspect, text
            inspector = inspect(connection)
            existing_tables = set(inspector.get_table_names())

            for table_name, table in Base.metadata.tables.items():
                if table_name not in existing_tables:
                    continue
                existing_cols = {c["name"].lower() for c in inspector.get_columns(table_name)}
                for col in table.columns:
                    if col.name.lower() not in existing_cols:
                        col_type = col.type.compile(dialect=connection.dialect)
                        nullable = "NULL"

                        col_type_str = str(col_type).upper()
                        is_text_type = any(t in col_type_str for t in ["TEXT", "BLOB", "JSON", "GEOMETRY"])

                        default_str = ""
                        if is_text_type:
                            default_str = ""
                        elif col.default is not None and getattr(col.default, "arg", None) is not None:
                            arg_val = getattr(col.default, "arg", None)
                            if isinstance(arg_val, (int, float)):
                                default_str = f" DEFAULT {arg_val}"
                            elif isinstance(arg_val, str):
                                default_str = f" DEFAULT '{arg_val}'"
                        elif col.nullable:
                            default_str = " DEFAULT NULL"
                        else:
                            if "DATETIME" in col_type_str or "TIMESTAMP" in col_type_str:
                                default_str = " DEFAULT CURRENT_TIMESTAMP"
                            elif "INT" in col_type_str or "BOOL" in col_type_str or "FLOAT" in col_type_str:
                                default_str = " DEFAULT 0"
                            else:
                                default_str = " DEFAULT ''"
                        
                        alter_stmt = f"ALTER TABLE `{table_name}` ADD COLUMN `{col.name}` {col_type} {nullable}{default_str}"

                        try:
                            connection.execute(text(alter_stmt))
                            logger.info(f"[mysql_client] Added missing column '{col.name}' to table '{table_name}'")
                        except Exception as ex:
                            logger.warning(f"[mysql_client] Could not add column '{col.name}' to '{table_name}': {ex}")

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(_sync_missing_columns)

        logger.info("[mysql_client] MySQL schema initialised successfully.")
        return True



    except Exception as exc:
        logger.error(f"[mysql_client] init_mysql() failed: {exc}")
        return False


async def ping_mysql() -> bool:
    """
    Health-check: return True if MySQL is reachable.
    Used by /api/health and startup checks.
    """
    engine = _get_async_engine()
    if engine is None:
        return False
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning(f"[mysql_client] ping_mysql() failed: {exc}")
        return False


def ping_mysql_sync() -> bool:
    """Sync version of ping_mysql for background workers."""
    engine = _get_sync_engine()
    if engine is None:
        return False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning(f"[mysql_client] ping_mysql_sync() failed: {exc}")
        return False


async def close_mysql() -> None:
    """Close async MySQL engine."""
    global _async_engine
    if _async_engine is not None:
        await _async_engine.dispose()
        _async_engine = None

