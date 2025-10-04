"""Test configuration and fixtures for MastoWatch test suite.

This module provides shared pytest fixtures for all tests, including:
- In-memory SQLite database setup
- Mock configurations
- Test client fixtures
"""

import os
import sys

# Ensure backend is on sys.path so imports like `import app.models` work
# regardless of the current working directory or pytest --rootdir used by VS Code.
ROOT = os.path.dirname(os.path.dirname(__file__))
BACKEND_PATH = os.path.join(ROOT, "backend")
if BACKEND_PATH not in sys.path:
    sys.path.insert(0, BACKEND_PATH)
import tempfile
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Set test environment variables before importing app modules
os.environ["TESTING"] = "true"
os.environ["DRY_RUN"] = "true"
os.environ["SKIP_STARTUP_VALIDATION"] = "true"
os.environ["INSTANCE_BASE"] = "https://test.example.com"
os.environ["BOT_TOKEN"] = "test_bot_token"
os.environ["ADMIN_TOKEN"] = "test_admin_token"
os.environ["API_KEY"] = "test_api_key"
os.environ["WEBHOOK_SECRET"] = "test_webhook_secret"
os.environ["REDIS_URL"] = "redis://localhost:6379/15"  # Use test Redis DB
os.environ["DATABASE_URL"] = "sqlite:///test.db"  # Temporary, will be overridden in fixtures
os.environ["UI_ORIGIN"] = "http://localhost:3000"  # Test UI origin

# Import models to ensure they're registered with Base.metadata
import app.models
from app.config import Settings
from app.db import Base, get_db
from app.main import app


@pytest.fixture(scope="session")
def test_settings():
    """Create test settings with in-memory database."""
    # Create a temporary file for SQLite database
    db_fd, db_path = tempfile.mkstemp()
    os.close(db_fd)

    # Override database URL to use SQLite
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

    settings = Settings()
    yield settings

    # Cleanup
    os.unlink(db_path)


@pytest.fixture(scope="session")
def test_engine(test_settings):
    """Create test database engine."""
    engine = create_engine(
        test_settings.DATABASE_URL,
        connect_args={"check_same_thread": False},  # Needed for SQLite
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def test_db_session(test_engine):
    """Create a test database session that rolls back after each test."""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSessionLocal()

    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="function")
def test_client(test_db_session):
    """Create test client with mocked database session."""

    def override_get_db():
        try:
            yield test_db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield client

    # Clean up
    app.dependency_overrides.clear()


@pytest.fixture
def mock_mastodon_client():
    """Create a mock Mastodon client for testing."""
    mock_client = MagicMock()

    # Mock common API responses
    mock_client.get_account_statuses.return_value = []
    mock_client.get_account.return_value = {
        "id": "123",
        "username": "testuser",
        "display_name": "Test User",
        "followers_count": 100,
        "following_count": 50,
        "statuses_count": 25,
        "created_at": "2023-01-01T00:00:00.000Z",
    }
    mock_client.submit_report.return_value = {"id": "report_123"}

    return mock_client


@pytest.fixture
def mock_redis():
    """Create a mock Redis client for testing."""
    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True
    mock_redis.exists.return_value = False
    return mock_redis


@pytest.fixture
def sample_account_data():
    """Sample account data for testing."""
    return {
        "id": "123456789",
        "username": "testuser",
        "display_name": "Test User",
        "note": "This is a test account",
        "followers_count": 100,
        "following_count": 50,
        "statuses_count": 25,
        "created_at": "2023-01-01T00:00:00.000Z",
        "locked": False,
        "bot": False,
        "discoverable": True,
    }


@pytest.fixture
def sample_status_data():
    """Sample status data for testing."""
    return {
        "id": "987654321",
        "content": "This is a test status",
        "created_at": "2023-01-01T12:00:00.000Z",
        "visibility": "public",
        "sensitive": False,
        "spoiler_text": "",
        "account": {"id": "123456789", "username": "testuser"},
        "media_attachments": [],
        "mentions": [],
        "tags": [],
        "reblogs_count": 0,
        "favourites_count": 0,
        "replies_count": 0,
    }


@pytest.fixture
def sample_webhook_report_payload():
    """Sample webhook payload for report.created event."""
    return {
        "event": "report.created",
        "created_at": "2023-01-01T12:00:00.000Z",
        "object": "report",
        "report": {
            "id": "report_123",
            "action_taken": False,
            "comment": "Test report",
            "created_at": "2023-01-01T12:00:00.000Z",
            "account": {"id": "123456789", "username": "testuser"},
            "target_account": {"id": "987654321", "username": "targetuser"},
            "statuses": [],
        },
    }


@pytest.fixture
def sample_webhook_status_payload():
    """Sample webhook payload for status.created event."""
    return {
        "event": "status.created",
        "created_at": "2023-01-01T12:00:00.000Z",
        "object": "status",
        "status": {
            "id": "987654321",
            "content": "This is a test status",
            "created_at": "2023-01-01T12:00:00.000Z",
            "account": {"id": "123456789", "username": "testuser"},
        },
    }
