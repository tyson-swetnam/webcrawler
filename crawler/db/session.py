"""
Database session management and connection pooling.

This module provides SQLAlchemy session creation and database engine configuration
with connection pooling for optimal performance.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Manages database connections and sessions with connection pooling.

    Provides thread-safe session creation and context managers for
    automatic session cleanup.
    """

    def __init__(self, database_url: str, pool_size: int = 10, echo: bool = False):
        """
        Initialize database manager with connection pooling.

        Args:
            database_url: PostgreSQL connection string
            pool_size: Maximum number of connections in pool
            echo: Whether to log SQL statements (for debugging)
        """
        self.engine = create_engine(
            database_url,
            pool_size=pool_size,
            max_overflow=20,
            pool_pre_ping=True,  # Verify connections before using
            pool_recycle=3600,   # Recycle connections after 1 hour
            echo=echo
        )

        # Create session factory
        session_factory = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False
        )

        # Thread-safe session
        self.Session = scoped_session(session_factory)

        logger.info(f"Database engine created with pool_size={pool_size}")

    def get_session(self):
        """
        Get a new database session.

        Returns:
            SQLAlchemy Session instance
        """
        return self.Session()

    @contextmanager
    def session_scope(self):
        """
        Provide a transactional scope for database operations.

        Usage:
            with db_manager.session_scope() as session:
                session.add(article)
                # Automatically commits or rolls back
        """
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()

    def create_tables(self):
        """
        Create all tables defined in models.

        Note: In production, use Alembic migrations instead.
        """
        from crawler.db.models import Base
        Base.metadata.create_all(self.engine)
        logger.info("Database tables created")

    def drop_tables(self):
        """
        Drop all tables (USE WITH CAUTION).

        Only use in development/testing environments.
        """
        from crawler.db.models import Base
        Base.metadata.drop_all(self.engine)
        logger.warning("All database tables dropped")

    def close(self):
        """
        Close all database connections.
        """
        self.Session.remove()
        self.engine.dispose()
        logger.info("Database connections closed")


# Global database manager instance (initialized by settings)
_db_manager = None


def init_db(database_url: str, pool_size: int = 10, echo: bool = False):
    """
    Initialize the global database manager.

    Args:
        database_url: PostgreSQL connection string
        pool_size: Connection pool size
        echo: Enable SQL logging

    Returns:
        DatabaseManager instance
    """
    global _db_manager
    _db_manager = DatabaseManager(database_url, pool_size, echo)
    return _db_manager


def get_db_manager() -> DatabaseManager:
    """
    Get the global database manager instance.

    Returns:
        DatabaseManager instance

    Raises:
        RuntimeError: If database not initialized
    """
    if _db_manager is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _db_manager


def SessionLocal():
    """
    Create a new database session.

    This is a convenience function for backward compatibility.

    Returns:
        SQLAlchemy Session instance
    """
    return get_db_manager().get_session()


@contextmanager
def get_db():
    """
    Get a database session with automatic cleanup.

    Usage:
        with get_db() as db:
            articles = db.query(Article).all()
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
