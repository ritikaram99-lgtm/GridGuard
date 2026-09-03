"""Database setup, session management, and connection handling."""

import logging
import time
from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from app.db.base import Base
from app.utils.config import get_database_url

logger = logging.getLogger(__name__)

# check_db_connection() is called on every forecast/risk request (each of
# db_service.py's record_* helpers calls it first). Without caching, a page
# that fans out to many feeders pays a fresh connection attempt every time --
# cheap when the DB is up, but a multi-second timeout on EVERY call when it's
# down, since nothing else in the request path is that slow (measured: ~4s
# per check while Postgres was unreachable, dominating total page load time).
# This cache changes no data/numbers -- it only avoids re-checking
# connectivity more often than once per _CHECK_TTL_SECONDS.
_CHECK_TTL_SECONDS = 5.0
_last_check_result: bool = False
_last_check_time: float = 0.0

# Retrieve database URL from config
DATABASE_URL = get_database_url()

# Create SQLAlchemy engine lazily with pre-ping validation
try:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
except Exception as err:
    logger.warning(f"SQLAlchemy engine setup initialized with fallback: {err}")
    engine = create_engine("sqlite:///:memory:", echo=False)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connection(force: bool = False) -> bool:
    """Test whether the PostgreSQL database is currently reachable.

    Result is cached for _CHECK_TTL_SECONDS (see module docstring) since this
    is called on every forecast/risk request -- pass force=True to bypass the
    cache (e.g. for the explicit /api/db/status endpoint, which should always
    reflect the current instant, not a stale cached value)."""
    global _last_check_result, _last_check_time

    now = time.monotonic()
    if not force and (now - _last_check_time) < _CHECK_TTL_SECONDS:
        return _last_check_result

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        _last_check_result = True
    except Exception as err:
        logger.debug(f"Database connection check failed: {err}")
        _last_check_result = False
    _last_check_time = now
    return _last_check_result


def init_db() -> bool:
    """Safely initialize database tables and seed feeders if database is reachable."""
    if not check_db_connection():
        logger.info("PostgreSQL database unavailable; skipping automatic schema creation.")
        return False

    try:
        logger.info("Initializing database tables via SQLAlchemy metadata...")
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables initialized successfully.")
        
        # Seed baseline feeders idempotently
        from app.services.db_service import seed_feeders_if_needed
        seed_feeders_if_needed()
        return True
    except Exception as err:
        logger.warning(f"Error during database table initialization: {err}")
        return False
