"""
Pytest configuration for API tests.

Uses SQLite in-memory database (shared via a static connection) so tests run
without a live PostgreSQL instance. GeoAlchemy2 PostGIS types are replaced with
Text columns for SQLite compatibility.
"""
import os

# Set env vars BEFORE any app module is imported
os.environ["DATABASE_URL"] = "sqlite://"
os.environ.setdefault("SENTINEL_HUB_CLIENT_ID", "test")
os.environ.setdefault("SENTINEL_HUB_CLIENT_SECRET", "test")
os.environ.setdefault("GROQ_API_KEY", "test")
os.environ.setdefault("SENDGRID_API_KEY", "test")
os.environ.setdefault("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool, event as sa_event, Text
from sqlalchemy.orm import sessionmaker

# Import app modules — DATABASE_URL is already set
import apps.api.database as _db_module
from apps.api.database import Base, get_db
from apps.api.main import app

# ── Shared in-memory SQLite engine (StaticPool keeps the same connection) ──────
test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@sa_event.listens_for(test_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# Redirect the module-level engine so all routes use our test engine
_db_module.engine = test_engine
_db_module.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="function", autouse=True)
def setup_db():
    """Create all tables before each test and drop them after."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def client(setup_db):  # depends on setup_db so tables exist when client is used
    return TestClient(app)


@pytest.fixture
def db_session(setup_db):
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Helpers ────────────────────────────────────────────────────────────────────

SAMPLE_GEOM = {
    "type": "Polygon",
    "coordinates": [
        [
            [77.0, 13.0],
            [77.5, 13.0],
            [77.5, 13.5],
            [77.0, 13.5],
            [77.0, 13.0],
        ]
    ],
}


def make_region_payload(**kwargs):
    defaults = {
        "name": "Test Region",
        "geom": SAMPLE_GEOM,
        "detection_types": ["construction", "deforestation"],
        "cadence": 24,
        "owner_email": "test@example.com",
    }
    defaults.update(kwargs)
    return defaults
