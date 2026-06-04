"""
Admin endpoints — manual scan triggers and ops.

Celery is used when Redis is available. Falls back to running the scan
logic synchronously in the same process (local dev without Redis).
"""
import json
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apps.api.database import get_db
from apps.api.models import Region

logger = logging.getLogger(__name__)
router = APIRouter()


def _run_scan_sync(region_id: int) -> Dict[str, Any]:
    """Run the full scan pipeline synchronously (no Celery required)."""
    import os
    from datetime import datetime, timedelta, timezone

    from apps.api.database import SessionLocal
    from apps.api.models import Event, AlertSubscription
    from apps.api.services.classifier import EventClassifier
    from apps.api.services.explainer import EventExplainer
    from apps.api.services.mock_imagery import MockImageryProvider
    from apps.worker.tasks import _region_bbox, _tile_url

    db = SessionLocal()
    try:
        region = db.query(Region).filter(Region.id == region_id).first()
        if not region:
            return {"error": "region_not_found"}

        bbox = _region_bbox(region)
        if not bbox:
            return {"error": "no_bbox"}

        det_types = region.detection_types or ["construction"]
        if isinstance(det_types, str):
            det_types = json.loads(det_types)

        now = datetime.now(tz=timezone.utc)
        after_start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        after_end = now.strftime("%Y-%m-%d")
        before_start = (now - timedelta(days=21)).strftime("%Y-%m-%d")
        before_end = (now - timedelta(days=14)).strftime("%Y-%m-%d")

        # Try real imagery first, fall back to mock
        before_s2 = after_s2 = None
        planet_key = os.environ.get("PLANET_API_KEY", "")
        sh_key = os.environ.get("SENTINEL_HUB_CLIENT_ID", "")

        if planet_key and planet_key not in ("test", "PLAKyour-planet-labs-api-key"):
            try:
                from apps.api.services.imagery import PlanetFetcher
                from apps.worker.tasks import _ps_to_s2_compat
                planet = PlanetFetcher(api_key=planet_key)
                before_s2 = _ps_to_s2_compat(planet.get_planetscope_composite(bbox, before_start, before_end))
                after_s2 = _ps_to_s2_compat(planet.get_planetscope_composite(bbox, after_start, after_end))
            except Exception as exc:
                logger.warning("Planet fetch failed, using mock: %s", exc)

        if before_s2 is None:
            mock = MockImageryProvider.for_region(det_types, seed=region_id)
            before_s2 = mock.before_s2()
            after_s2 = mock.after_s2()

        before_sar = after_sar = None
        if "flood" in det_types:
            mock_sar = MockImageryProvider(change_type="flood", seed=region_id)
            before_sar = mock_sar.before_sar()
            after_sar = mock_sar.after_sar()

        classifier = EventClassifier(detection_types=det_types, min_confidence=0.1, bbox=bbox)
        result = classifier.classify(before_s2, after_s2, before_sar, after_sar)

        if result is None:
            return {"region_id": region_id, "result": "no_change"}

        description = EventExplainer().explain({
            "detected_type": result.detected_type,
            "confidence": result.confidence,
            "lat": result.lat,
            "lon": result.lon,
            "region_name": region.name,
            "first_seen": now.isoformat(),
            "before_date": before_start,
            "after_date": after_end,
        })

        event = Event(
            region_id=region_id,
            detected_type=result.detected_type,
            confidence=result.confidence,
            lat=result.lat,
            lon=result.lon,
            description=description,
            before_tile_url=_tile_url(bbox, before_start, before_end),
            after_tile_url=_tile_url(bbox, after_start, after_end),
        )
        db.add(event)
        db.commit()
        db.refresh(event)

        return {
            "region_id": region_id,
            "event_id": event.id,
            "detected_type": result.detected_type,
            "confidence": round(result.confidence, 3),
            "description": description,
            "mode": "sync",
        }
    finally:
        db.close()


def _try_celery(task_fn, *args, queue: str = "scanning") -> Dict[str, Any]:
    """Try to dispatch via Celery; return None if Redis is unavailable."""
    try:
        task = task_fn.apply_async(args=list(args), queue=queue)
        return {"queued": True, "task_id": task.id, "mode": "celery"}
    except Exception:
        return None


@router.post("/scan/{region_id}", response_model=Dict[str, Any])
def trigger_scan(region_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Manually trigger a scan for a specific region (Celery if available, else sync)."""
    region = db.query(Region).filter(Region.id == region_id).first()
    if not region:
        raise HTTPException(status_code=404, detail="Region not found")

    from apps.worker.tasks import scan_region
    result = _try_celery(scan_region, region_id)
    if result:
        result["region_id"] = region_id
        return result

    logger.info("Redis unavailable — running scan synchronously for region %d", region_id)
    return _run_scan_sync(region_id)


@router.post("/scan-all", response_model=Dict[str, Any])
def trigger_scan_all(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Trigger a scan cycle for all regions."""
    regions = db.query(Region).all()
    if not regions:
        raise HTTPException(status_code=404, detail="No regions found")

    from apps.worker.tasks import scan_region
    results = []
    for region in regions:
        celery_result = _try_celery(scan_region, region.id)
        if celery_result:
            results.append({"region_id": region.id, **celery_result})
        else:
            res = _run_scan_sync(region.id)
            results.append(res)

    return {
        "total": len(results),
        "results": results,
    }
