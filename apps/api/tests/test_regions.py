"""
Tests for the /api/regions endpoints.
"""
import json
import pytest
from fastapi.testclient import TestClient

from apps.api.tests.conftest import make_region_payload, SAMPLE_GEOM


class TestCreateRegion:
    def test_create_region_success(self, client: TestClient):
        payload = make_region_payload()
        resp = client.post("/api/regions/", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Region"
        assert data["cadence"] == 24
        assert data["owner_email"] == "test@example.com"
        assert "id" in data
        assert "construction" in data["detection_types"]

    def test_create_region_invalid_detection_type(self, client: TestClient):
        payload = make_region_payload(detection_types=["invalid_type"])
        resp = client.post("/api/regions/", json=payload)
        assert resp.status_code == 422

    def test_create_region_invalid_cadence(self, client: TestClient):
        payload = make_region_payload(cadence=0)
        resp = client.post("/api/regions/", json=payload)
        assert resp.status_code == 422

    def test_create_region_non_polygon_geom(self, client: TestClient):
        payload = make_region_payload(
            geom={"type": "Point", "coordinates": [77.0, 13.0]}
        )
        resp = client.post("/api/regions/", json=payload)
        assert resp.status_code == 400

    def test_create_region_missing_name(self, client: TestClient):
        payload = make_region_payload()
        del payload["name"]
        resp = client.post("/api/regions/", json=payload)
        assert resp.status_code == 422


class TestListRegions:
    def test_list_empty(self, client: TestClient):
        resp = client.get("/api/regions/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_after_create(self, client: TestClient):
        client.post("/api/regions/", json=make_region_payload(name="Region A"))
        client.post("/api/regions/", json=make_region_payload(name="Region B"))
        resp = client.get("/api/regions/")
        assert resp.status_code == 200
        names = [r["name"] for r in resp.json()]
        assert "Region A" in names
        assert "Region B" in names


class TestGetRegion:
    def test_get_existing(self, client: TestClient):
        create_resp = client.post("/api/regions/", json=make_region_payload())
        region_id = create_resp.json()["id"]

        resp = client.get(f"/api/regions/{region_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == region_id

    def test_get_nonexistent(self, client: TestClient):
        resp = client.get("/api/regions/99999")
        assert resp.status_code == 404


class TestDeleteRegion:
    def test_delete_existing(self, client: TestClient):
        create_resp = client.post("/api/regions/", json=make_region_payload())
        region_id = create_resp.json()["id"]

        resp = client.delete(f"/api/regions/{region_id}")
        assert resp.status_code == 204

        # Verify it's gone
        get_resp = client.get(f"/api/regions/{region_id}")
        assert get_resp.status_code == 404

    def test_delete_nonexistent(self, client: TestClient):
        resp = client.delete("/api/regions/99999")
        assert resp.status_code == 404

    def test_delete_cascades_to_events(self, client: TestClient, db_session):
        from apps.api.models import Event

        create_resp = client.post("/api/regions/", json=make_region_payload())
        region_id = create_resp.json()["id"]

        # Manually insert an event
        event = Event(
            region_id=region_id,
            detected_type="construction",
            confidence=0.8,
        )
        db_session.add(event)
        db_session.commit()

        # Delete the region
        client.delete(f"/api/regions/{region_id}")

        # Event should be gone (cascade)
        remaining = db_session.query(Event).filter(Event.region_id == region_id).count()
        assert remaining == 0
