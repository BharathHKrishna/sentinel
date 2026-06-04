"""
Tests for the /api/events endpoints.
"""
from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient

from apps.api.models import Event, Region
from apps.api.tests.conftest import make_region_payload


def _create_region(client: TestClient) -> int:
    """Helper: create a region and return its id."""
    resp = client.post("/api/regions/", json=make_region_payload())
    assert resp.status_code == 201
    return resp.json()["id"]


def _insert_event(db_session, region_id: int, **kwargs) -> Event:
    """Helper: insert an event directly into the DB."""
    defaults = {
        "detected_type": "construction",
        "confidence": 0.75,
        "lat": 13.2,
        "lon": 77.2,
        "description": "Test description",
    }
    defaults.update(kwargs)
    event = Event(region_id=region_id, **defaults)
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    return event


class TestListEvents:
    def test_list_empty(self, client: TestClient):
        resp = client.get("/api/events/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_all(self, client: TestClient, db_session):
        rid = _create_region(client)
        _insert_event(db_session, rid, detected_type="fire")
        _insert_event(db_session, rid, detected_type="flood")

        resp = client.get("/api/events/")
        assert resp.status_code == 200
        types = {e["detected_type"] for e in resp.json()}
        assert "fire" in types
        assert "flood" in types

    def test_filter_by_region_id(self, client: TestClient, db_session):
        rid1 = _create_region(client)
        rid2 = _create_region(client)
        _insert_event(db_session, rid1, detected_type="construction")
        _insert_event(db_session, rid2, detected_type="solar")

        resp = client.get(f"/api/events/?region_id={rid1}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["detected_type"] == "construction"

    def test_filter_by_type(self, client: TestClient, db_session):
        rid = _create_region(client)
        _insert_event(db_session, rid, detected_type="fire")
        _insert_event(db_session, rid, detected_type="flood")

        resp = client.get("/api/events/?detected_type=fire")
        assert resp.status_code == 200
        data = resp.json()
        assert all(e["detected_type"] == "fire" for e in data)

    def test_filter_by_since(self, client: TestClient, db_session):
        rid = _create_region(client)
        now = datetime.now(tz=timezone.utc)
        old_event = _insert_event(db_session, rid, detected_type="flood")
        # Manually backdate the old event
        old_event.first_seen = now - timedelta(days=30)
        db_session.commit()

        new_event = _insert_event(db_session, rid, detected_type="fire")

        since = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        resp = client.get(f"/api/events/?since={since}")
        assert resp.status_code == 200
        ids = [e["id"] for e in resp.json()]
        assert new_event.id in ids
        assert old_event.id not in ids

    def test_pagination(self, client: TestClient, db_session):
        rid = _create_region(client)
        for i in range(5):
            _insert_event(db_session, rid, detected_type="solar")

        resp = client.get("/api/events/?limit=2&offset=0")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

        resp2 = client.get("/api/events/?limit=2&offset=2")
        assert resp2.status_code == 200
        assert len(resp2.json()) == 2

    def test_limit_validation(self, client: TestClient):
        resp = client.get("/api/events/?limit=9999")
        # limit capped at 1000 → 422
        assert resp.status_code == 422


class TestGetEvent:
    def test_get_existing_event(self, client: TestClient, db_session):
        rid = _create_region(client)
        event = _insert_event(db_session, rid, detected_type="construction", confidence=0.9)

        resp = client.get(f"/api/events/{event.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == event.id
        assert data["detected_type"] == "construction"
        assert abs(data["confidence"] - 0.9) < 0.001

    def test_get_nonexistent_event(self, client: TestClient):
        resp = client.get("/api/events/99999")
        assert resp.status_code == 404

    def test_event_has_all_fields(self, client: TestClient, db_session):
        rid = _create_region(client)
        event = _insert_event(
            db_session,
            rid,
            detected_type="deforestation",
            confidence=0.65,
            lat=12.5,
            lon=76.8,
            description="Forest clearing detected.",
            before_tile_url="https://example.com/before.png",
            after_tile_url="https://example.com/after.png",
        )

        resp = client.get(f"/api/events/{event.id}")
        data = resp.json()
        assert data["lat"] == 12.5
        assert data["lon"] == 76.8
        assert data["description"] == "Forest clearing detected."
        assert data["before_tile_url"] == "https://example.com/before.png"
        assert data["after_tile_url"] == "https://example.com/after.png"
