"""
Pytest Configuration & Database Isolation Fixture
--------------------------------------------------
Ensures complete test isolation from the development database:
1. Enforces that all test suites execute exclusively against a dedicated test database ('neondb_test').
2. Uses nested transactions (SAVEPOINT) to automatically roll back all test modifications after every test.
3. Overrides FastAPI's `get_db` dependency and database SessionLocal with the isolated test session.
4. Preserves development and production database records from accidental alteration or deletion.
"""

import os
import pytest
from urllib.parse import urlsplit, urlunsplit
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from httpx import AsyncClient, ASGITransport

from app.core.config import settings
from app.core.database import Base, get_db
import app.core.database as core_db
import app.middleware.api_key_gateway as gateway_middleware
from app.main import app


# 1. Resolve Dedicated Test Database URL
raw_test_url = os.getenv("TEST_DATABASE_URL") or settings.TEST_DATABASE_URL
if not raw_test_url:
    parts = urlsplit(settings.DATABASE_URL)
    db_name = parts.path.lstrip("/")
    if "test" not in db_name.lower():
        test_path = f"/{db_name}_test" if db_name else "/neondb_test"
    else:
        test_path = parts.path
    test_parts = parts._replace(path=test_path)
    raw_test_url = urlunsplit(test_parts)

TEST_DATABASE_URL = settings.assemble_db_connection(raw_test_url)

# Critical Safety Check: Prevent running against development or production databases
parsed_test = urlsplit(TEST_DATABASE_URL)
target_db = parsed_test.path.lstrip("/").split("?")[0].lower()
if "test" not in target_db:
    raise RuntimeError(
        f"CRITICAL SAFETY VIOLATION: Test suite attempted to connect to non-test database '{target_db}'! "
        "Tests must run exclusively against an isolated test database (e.g., 'neondb_test')."
    )

# 2. Initialize Dedicated Test Engine
test_engine = create_engine(
    TEST_DATABASE_URL,
    poolclass=QueuePool,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 15},
)

TestSessionLocal = sessionmaker(
    bind=test_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

# Global test session tracker for proxying
_active_test_session = None
_active_connection = None


class SessionLocalProxy:
    """Proxy callable that dynamically routes SessionLocal() calls to the current test transaction session."""
    def __call__(self, *args, **kwargs):
        if _active_connection is not None:
            return Session(bind=_active_connection, expire_on_commit=False)
        return TestSessionLocal(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(TestSessionLocal, name)


proxy_session_local = SessionLocalProxy()
core_db.engine = test_engine
core_db.SessionLocal = proxy_session_local
gateway_middleware.SessionLocal = proxy_session_local


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Verifies schema existence on test database once per session."""
    import app.models  # noqa
    Base.metadata.create_all(test_engine)
    yield


@pytest.fixture(scope="function", autouse=True)
def db_session_rollback():
    """
    Transactional rollback fixture for complete test isolation.
    Uses SQLAlchemy nested transactions (SAVEPOINT) so that:
    - Code can call session.commit() normally.
    - Each commit only closes the savepoint and opens a new one.
    - At the end of the test, trans.rollback() erases all inserted/modified rows.
    - Zero leftover rows are retained in the test database.
    """
    global _active_test_session, _active_connection

    connection = test_engine.connect()
    trans = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)

    # Begin first SAVEPOINT
    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def end_savepoint(session_obj, transaction):
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    # Reset auth rate limiter keys to ensure test isolation
    try:
        from app.core.redis import get_redis_client
        rc = get_redis_client()
        keys = rc.keys("ratelimit:auth:*")
        if keys:
            rc.delete(*keys)
    except Exception:
        pass

    _active_connection = connection
    _active_test_session = session

    def override_get_db():
        try:
            yield session
        except Exception:
            session.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db

    yield session

    # Teardown
    session.close()
    trans.rollback()
    connection.close()

    _active_connection = None
    _active_test_session = None
    app.dependency_overrides.pop(get_db, None)

    try:
        from app.core.redis import get_redis_client
        rc = get_redis_client()
        keys = rc.keys("ratelimit:auth:*")
        if keys:
            rc.delete(*keys)
    except Exception:
        pass


@pytest.fixture
async def client():
    """Asynchronous HTTP test client bound to FastAPI application."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
