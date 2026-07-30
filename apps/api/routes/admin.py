"""
Admin endpoints — manual scan triggers and ops.

Celery is used when Redis is available. Falls back to running the scan
logic synchronously in the same process (local dev without Redis).
"""
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from apps.api.database import get_db
from apps.api.models import Region

logger = logging.getLogger(__name__)
router = APIRouter()

# Long-lived pool (never shut down) so a stuck apply_async() thread can be
# abandoned via a timeout without blocking the caller — Celery/kombu's own
# connection-retry tuning wasn't reliably bounding the delay when REDIS_URL
# points at an unreachable broker.
_celery_dispatch_pool = ThreadPoolExecutor(max_workers=4)


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
                logger.warning("Planet fetch failed: %s", exc)

        if before_s2 is None:
            try:
                from apps.api.services.imagery import FreeS2Fetcher
                fetcher = FreeS2Fetcher()
                before_s2 = fetcher.get_composite(bbox, before_start, before_end)
                after_s2 = fetcher.get_composite(bbox, after_start, after_end)
                logger.info("Using free Sentinel-2 imagery for region %d", region_id)
            except Exception as exc:
                logger.warning("Free S2 fetch failed: %s", exc)

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


def _try_celery(task_fn, *args, queue: str = "scanning", timeout: float = 3.0) -> Dict[str, Any]:
    """
    Try to dispatch via Celery; return None if Redis is unavailable or the
    dispatch attempt doesn't complete within `timeout` seconds. Runs
    apply_async() on a worker thread so a stuck connection (e.g. Celery's
    internal retry/backoff on an unreachable broker) can be abandoned
    without blocking the caller.
    """
    future = _celery_dispatch_pool.submit(
        lambda: task_fn.apply_async(args=list(args), queue=queue)
    )
    try:
        task = future.result(timeout=timeout)
        return {"queued": True, "task_id": task.id, "mode": "celery"}
    except Exception:
        return None


def _run_scan_background(region_id: int) -> None:
    """Run the scan pipeline in a background thread (no Celery required)."""
    try:
        result = _run_scan_sync(region_id)
        logger.info("Background scan complete for region %d: %s", region_id, result)
    except Exception:
        import traceback
        logger.error("Background scan failed for region %d: %s", region_id, traceback.format_exc())


@router.post("/scan/{region_id}", response_model=Dict[str, Any])
def trigger_scan(
    region_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Manually trigger a scan for a specific region (Celery if available, else background task)."""
    region = db.query(Region).filter(Region.id == region_id).first()
    if not region:
        raise HTTPException(status_code=404, detail="Region not found")

    try:
        from apps.worker.tasks import scan_region
        result = _try_celery(scan_region, region_id)
        if result:
            result["region_id"] = region_id
            return result
    except Exception as exc:
        logger.warning("Celery dispatch failed: %s", exc)

    logger.info("Redis unavailable — running scan in background for region %d", region_id)
    background_tasks.add_task(_run_scan_background, region_id)
    return {"region_id": region_id, "queued": True, "mode": "background"}


@router.post("/scan-all", response_model=Dict[str, Any])
def trigger_scan_all(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
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
            background_tasks.add_task(_run_scan_background, region.id)
            results.append({"region_id": region.id, "queued": True, "mode": "background"})

    return {
        "total": len(results),
        "results": results,
    }
