"""Database initialization script module."""

import logging
from app.db.database import init_db as run_init_db

logger = logging.getLogger(__name__)


def init_db() -> bool:
    """Initialize database schemas and tables safely."""
    return run_init_db()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
