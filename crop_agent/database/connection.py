"""Database connection management for Crop Intelligence Agent.

Provides a thread-safe SQLAlchemy engine and session factory.
The database URL is read from environment (DATABASE_URL in .env).

Phase 1: SQLite (zero-setup local development)
Phase 2: PostgreSQL (change DATABASE_URL in .env — no code changes needed)

Usage:
    from crop_agent.database.connection import get_session, engine

    with get_session() as session:
        results = session.query(RawMandiPrice).all()
"""

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from crop_agent.config.logging_config import get_logger
from crop_agent.config.settings import DATABASE_URL

logger = get_logger(__name__)

# Create the engine — supports both SQLite and PostgreSQL via DATABASE_URL
_connect_args: dict[str, bool] = {}
if DATABASE_URL.startswith("sqlite"):
    # SQLite requires check_same_thread=False for multi-threaded use (APScheduler)
    _connect_args = {"check_same_thread": False}

engine: Engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    echo=False,  # Set True for SQL query debugging
    pool_pre_ping=True,  # Validates connection before use — prevents stale connections
)

# Enable WAL mode for SQLite — allows concurrent reads during writes
if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection: Any, connection_record: object) -> None:
        """Enable WAL mode and foreign keys for SQLite connections.

        Args:
        ----
            dbapi_connection: The raw DBAPI connection object.
            connection_record: The connection pool record.

        """
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

# Session factory — use this everywhere, not raw engine
SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,  # Objects remain accessible after commit
)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Provide a transactional database session as a context manager.

    Automatically commits on success and rolls back on any exception.
    Always closes the session when done.

    Yields:
    ------
        A SQLAlchemy Session object.

    Raises:
    ------
        Exception: Re-raises any exception after rolling back the transaction.

    Example:
    -------
        with get_session() as session:
            price = RawMandiPrice(crop="Paddy", price_inr_per_qtl=2200.0)
            session.add(price)

    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
        logger.debug("database.session_committed")
    except Exception as exc:
        session.rollback()
        logger.error(
            "database.session_rolled_back",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise
    finally:
        session.close()


def verify_connection() -> bool:
    """Verify the database connection is working.

    Returns
    -------
        True if connection is healthy, False otherwise.

    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("database.connection_verified", url=DATABASE_URL.split("@")[-1])
        return True
    except Exception as exc:
        logger.error(
            "database.connection_failed",
            error=str(exc),
            url=DATABASE_URL.split("@")[-1],
        )
        return False
