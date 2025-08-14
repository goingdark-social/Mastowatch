"""Test configuration and fixtures for MastoWatch test suite.

This module provides shared pytest fixtures for all tests, including:
- In-memory SQLite database setup
- Mock configurations
- Test client fixtures
"""

import os
import sys
import tempfile
import types
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

mastodon_pkg = types.ModuleType("app.clients.mastodon")
mastodon_pkg.__path__ = []

client_mod = types.ModuleType("app.clients.mastodon.client")


class AuthenticatedClient:  # noqa: D401
    def __init__(self, *_, **__):
        pass


class Client:  # noqa: D401
    def __init__(self, *_, **__):
        pass


client_mod.AuthenticatedClient = AuthenticatedClient
client_mod.Client = Client
mastodon_pkg.AuthenticatedClient = AuthenticatedClient
mastodon_pkg.Client = Client

api_pkg = types.ModuleType("app.clients.mastodon.api")
api_pkg.__path__ = []

accounts_pkg = types.ModuleType("app.clients.mastodon.api.accounts")
accounts_pkg.__path__ = []

get_account_mod = types.ModuleType("app.clients.mastodon.api.accounts.get_account")


def _get_account_sync(*_, **__):
    return None


get_account_mod.sync = _get_account_sync

get_account_statuses_mod = types.ModuleType("app.clients.mastodon.api.accounts.get_account_statuses")


def _get_account_statuses_sync(*_, **__):
    return []


get_account_statuses_mod.sync = _get_account_statuses_sync

get_accounts_verify_credentials_mod = types.ModuleType(
    "app.clients.mastodon.api.accounts.get_accounts_verify_credentials"
)


def _get_accounts_verify_credentials_sync(*_, **__):
    return None


get_accounts_verify_credentials_mod.sync = _get_accounts_verify_credentials_sync
get_accounts_verify_credentials_mod.asyncio = _get_accounts_verify_credentials_sync

models_pkg = types.ModuleType("app.clients.mastodon.models")
models_pkg.__path__ = []

create_report_body_mod = types.ModuleType("app.clients.mastodon.models.create_report_body")


class CreateReportBody:
    def __init__(self, account_id, comment, category, forward, status_ids, rule_ids):
        self.account_id = account_id
        self.comment = comment
        self.category = category
        self.forward = forward
        self.status_ids = status_ids
        self.rule_ids = rule_ids

    def to_dict(self):
        return {
            "account_id": self.account_id,
            "comment": self.comment,
            "category": self.category,
            "forward": self.forward,
            "status_ids": self.status_ids,
            "rule_ids": self.rule_ids,
        }


create_report_body_mod.CreateReportBody = CreateReportBody

reports_pkg = types.ModuleType("app.clients.mastodon.api.reports")
reports_pkg.__path__ = []

create_report_mod = types.ModuleType("app.clients.mastodon.api.reports.create_report")


def _create_report_sync(*_, **__):
    return None


create_report_mod.sync = _create_report_sync
instance_pkg = types.ModuleType("app.clients.mastodon.api.instance")
instance_pkg.__path__ = []
get_instance_mod = types.ModuleType("app.clients.mastodon.api.instance.get_instance")


def _get_instance_sync(*_, **__):
    return None


get_instance_mod.sync = _get_instance_sync
get_instance_rules_mod = types.ModuleType("app.clients.mastodon.api.instance.get_instance_rules")


def _get_instance_rules_sync(*_, **__):
    return []


get_instance_rules_mod.sync = _get_instance_rules_sync

sys.modules.update(
    {
        "app.clients.mastodon": mastodon_pkg,
        "app.clients.mastodon.client": client_mod,
        "app.clients.mastodon.api": api_pkg,
        "app.clients.mastodon.api.accounts": accounts_pkg,
        "app.clients.mastodon.api.accounts.get_account": get_account_mod,
        "app.clients.mastodon.api.accounts.get_account_statuses": get_account_statuses_mod,
        "app.clients.mastodon.api.accounts.get_accounts_verify_credentials": get_accounts_verify_credentials_mod,
        "app.clients.mastodon.models": models_pkg,
        "app.clients.mastodon.models.create_report_body": create_report_body_mod,
        "app.clients.mastodon.api.reports": reports_pkg,
        "app.clients.mastodon.api.reports.create_report": create_report_mod,
        "app.clients.mastodon.api.instance": instance_pkg,
        "app.clients.mastodon.api.instance.get_instance": get_instance_mod,
        "app.clients.mastodon.api.instance.get_instance_rules": get_instance_rules_mod,
    }
)

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
