"""Database initialization script.

Run this once to create all tables in the database.
Usage:
    python -m crop_agent.database.init_db
    # or
    make db-init
"""

import sys

from crop_agent.config.logging_config import configure_logging, get_logger
from crop_agent.database.connection import engine, verify_connection
from crop_agent.database.models import Base

configure_logging()
logger = get_logger(__name__)


def init_db() -> None:
    """Create all database tables if they do not exist.

    Safe to run multiple times — uses CREATE TABLE IF NOT EXISTS semantics
    via SQLAlchemy's create_all(checkfirst=True).

    Raises:
        SystemExit: If the database connection cannot be established.
    """
    logger.info("database.init_start")

    if not verify_connection():
        logger.error("database.init_failed", reason="Cannot connect to database")
        sys.exit(1)

    try:
        Base.metadata.create_all(bind=engine, checkfirst=True)
        table_names = list(Base.metadata.tables.keys())
        logger.info(
            "database.init_complete",
            tables_created=len(table_names),
            tables=table_names,
        )
        print(f"✅ Database initialized with {len(table_names)} tables.")
        for name in sorted(table_names):
            print(f"   • {name}")
    except Exception as exc:
        logger.error(
            "database.init_error",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise


if __name__ == "__main__":
    init_db()
