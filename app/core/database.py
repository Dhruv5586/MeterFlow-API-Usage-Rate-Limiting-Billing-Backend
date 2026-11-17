"""
Database Engine & Session Management (SQLAlchemy 2.0)
-----------------------------------------------------
Configures the connection engine, connection pool, session maker,
and the FastAPI `get_db` dependency with proper lifecycle management.
"""

import logging
from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import SQLAlchemyError, OperationalError

from app.core.config import settings
from app.core.exceptions import DatabaseConnectionError

logger = logging.getLogger("meterflow.database")

# Declarative Base for all ORM models
Base = declarative_base()

# Configure SQLAlchemy 2.0 Engine with QueuePool connection pooling
# Note: connect_args={"connect_timeout": 10} ensures fast failure if DB is unreachable
engine = create_engine(
    settings.DATABASE_URL,
    poolclass=QueuePool,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,  # Tests connections on checkout to discard dead connections
    echo=settings.DEBUG,
    connect_args={"connect_timeout": 10},
)

# Session factory bound to the engine
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency yielding a managed database session per request.
    Ensures rollback on unhandled errors and guaranteed session closure.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as exc:
        db.rollback()
        logger.error(f"Transaction rolled back due to error: {exc}")
        raise
    finally:
        db.close()


def check_database_health() -> bool:
    """
    Performs a lightweight query (SELECT 1) to verify database connectivity.
    Returns True if healthy; raises DatabaseConnectionError if unavailable.
    """
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1")).scalar()
            return result == 1
    except OperationalError as op_err:
        logger.error(f"Database health check failed (OperationalError): {op_err}")
        raise DatabaseConnectionError("Database is unreachable or rejecting connections.") from op_err
    except SQLAlchemyError as sa_err:
        logger.error(f"Database health check failed (SQLAlchemyError): {sa_err}")
        raise DatabaseConnectionError(f"Database health check error: {sa_err}") from sa_err
