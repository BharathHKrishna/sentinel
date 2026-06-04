"""Tests for the stats and admin endpoints."""
import json

import pytest
from fastapi.testclient import TestClient


def test_stats_empty_db(client):
    """Stats endpoint returns zeros on empty DB."""
    resp = client.get("/api/stats/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_regions"] == 0
    assert data["total_events"] == 0
    assert data["events_7d"] == 0


def test_stats_with_data(client):
    """Stats reflect inserted regions and events."""
    # Create a region
    region_payload = {
        "name": "Stats Test Region",
        "geom": {
            "type": "Polygon",
            "coordinates": [[[76.9, 13.2], [77.4, 13.2], [77.4, 13.7], [76.9, 13.7], [76.9, 13.2]]],
        },
        "detection_types": ["construction"],
        "cadence": 24,
    }
    r = client.post("/api/regions/", json=region_payload)
    assert r.status_code == 201
    region_id = r.json()["id"]

    resp = client.get("/api/stats/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_regions"] == 1


def test_event_feedback(client):
    """Feedback endpoint updates is_false_positive."""
    # Create region + event via the API
    region_payload = {
        "name": "Feedback Test",
        "geom": {
            "type": "Polygon",
            "coordinates": [[[76.9, 13.2], [77.4, 13.2], [77.4, 13.7], [76.9, 13.7], [76.9, 13.2]]],
        },
        "detection_types": ["fire"],
        "cadence": 24,
    }
    region_id = client.post("/api/regions/", json=region_payload).json()["id"]

    # Insert event directly via the DB (bypassing worker)
    from apps.api.models import Event
    from apps.api.database import SessionLocal
    db = SessionLocal()
    event = Event(region_id=region_id, detected_type="fire", confidence=0.7)
    db.add(event)
    db.commit()
    db.refresh(event)
    event_id = event.id
    db.close()

    # Submit false-positive feedback
    resp = client.patch(f"/api/events/{event_id}/feedback", json={"is_false_positive": True})
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_false_positive"] is True

    # Confirm it
    resp2 = client.patch(f"/api/events/{event_id}/feedback", json={"is_false_positive": False})
    assert resp2.status_code == 200
    assert resp2.json()["is_false_positive"] is False
