"""Database setup, session management, and connection handling."""

import logging
from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from app.db.base import Base
from app.utils.config import get_database_url

logger = logging.getLogger(__name__)

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


def check_db_connection() -> bool:
    """Test whether the PostgreSQL database is currently reachable."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception as err:
        logger.debug(f"Database connection check failed: {err}")
        return False


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
