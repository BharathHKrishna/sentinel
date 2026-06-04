"""
Celery tasks for the Sentinel worker.

Task graph:
  scan_all_regions
    └─ scan_region(region_id)
         └─ classify_change(event_id)
              └─ send_alert(event_id, subscription_id)   ×N subscribers

  dispatch_pending_alerts  (periodic safety net)
"""
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

from apps.worker.celery_app import app

logger = logging.getLogger(__name__)


def _get_db_session():
    """Create a new SQLAlchemy session (not using FastAPI's dependency injection)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    Session = sessionmaker(bind=engine)
    return Session()


# ── scan_all_regions ───────────────────────────────────────────────────────────

@app.task(name="apps.worker.tasks.scan_all_regions", bind=True, max_retries=3)
def scan_all_regions(self) -> Dict[str, Any]:
    """
    Periodic task: query all regions and dispatch scan_region for each one
    whose cadence is due.
    """
    db = _get_db_session()
    try:
        from apps.api.models import Region

        regions = db.query(Region).all()
        dispatched = []

        now = datetime.now(tz=timezone.utc)
        for region in regions:
            # Check if it's time to scan this region based on cadence (hours)
            # We look for the most recent event; if none, scan immediately.
            from apps.api.models import Event
            last_event = (
                db.query(Event)
                .filter(Event.region_id == region.id)
                .order_by(Event.created_at.desc())
                .first()
            )

            if last_event is None:
                due = True
            else:
                next_scan_at = last_event.created_at + timedelta(hours=region.cadence)
                # Make next_scan_at timezone-aware if naive
                if next_scan_at.tzinfo is None:
                    next_scan_at = next_scan_at.replace(tzinfo=timezone.utc)
                due = now >= next_scan_at

            if due:
                scan_region.apply_async(
                    args=[region.id],
                    queue="scanning",
                )
                dispatched.append(region.id)
                logger.info("Dispatched scan for region %d (%s)", region.id, region.name)

        return {"dispatched": dispatched, "total_regions": len(regions)}
    finally:
        db.close()


# ── scan_region ────────────────────────────────────────────────────────────────

@app.task(name="apps.worker.tasks.scan_region", bind=True, max_retries=3,
          default_retry_delay=300)
def scan_region(self, region_id: int) -> Dict[str, Any]:
    """
    Fetch before/after imagery for a region and run the classification pipeline.
    If a significant change is detected, creates an Event row and dispatches
    classify_change.
    """
    db = _get_db_session()
    try:
        from apps.api.models import Region, Event

        region = db.query(Region).filter(Region.id == region_id).first()
        if not region:
            logger.error("Region %d not found", region_id)
            return {"error": "region_not_found"}

        # Derive bounding box from PostGIS geometry
        bbox = _region_bbox(region)
        if bbox is None:
            logger.error("Could not extract bbox for region %d", region_id)
            return {"error": "no_bbox"}

        # Date windows: compare last 7 days vs 14-21 days ago
        now = datetime.now(tz=timezone.utc)
        after_start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        after_end = now.strftime("%Y-%m-%d")
        before_start = (now - timedelta(days=21)).strftime("%Y-%m-%d")
        before_end = (now - timedelta(days=14)).strftime("%Y-%m-%d")

        # Fetch imagery — Planet (3 m, preferred) with Sentinel-2 (10 m) fallback
        from apps.api.services.imagery import SentinelHubFetcher, PlanetFetcher

        before_s2 = after_s2 = None
        planet_key = os.environ.get("PLANET_API_KEY", "")

        if planet_key:
            try:
                planet = PlanetFetcher(api_key=planet_key)
                before_ps = planet.get_planetscope_composite(bbox, before_start, before_end)
                after_ps = planet.get_planetscope_composite(bbox, after_start, after_end)
                # Convert PlanetScope (B,G,R,NIR) to S2-compatible 12-band layout
                # by padding to match the generic detector's band expectations
                before_s2 = _ps_to_s2_compat(before_ps)
                after_s2 = _ps_to_s2_compat(after_ps)
                logger.info("Using PlanetScope imagery for region %d", region_id)
            except Exception as exc:
                logger.warning("Planet fetch failed for region %d, falling back to S2: %s", region_id, exc)

        sh_client = os.environ.get("SENTINEL_HUB_CLIENT_ID", "")

        if before_s2 is None and sh_client and sh_client != "your-sentinel-hub-client-id":
            try:
                fetcher = SentinelHubFetcher()
                before_s2 = fetcher.get_sentinel2_composite(bbox, before_start, before_end)
                after_s2 = fetcher.get_sentinel2_composite(bbox, after_start, after_end)
            except Exception as exc:
                logger.warning("S2 imagery fetch failed for region %d: %s", region_id, exc)

        # Fall back to mock imagery for local dev / CI
        if before_s2 is None:
            from apps.api.services.mock_imagery import MockImageryProvider
            detection_types = region.detection_types or ["construction"]
            if isinstance(detection_types, str):
                import json as _json
                detection_types = _json.loads(detection_types)
            mock = MockImageryProvider.for_region(detection_types, seed=region_id)
            before_s2 = mock.before_s2()
            after_s2 = mock.after_s2()
            logger.info("Using mock imagery for region %d (no satellite credentials)", region_id)

        # SAR for flood detection (best-effort — Sentinel-1 only)
        before_sar = None
        after_sar = None
        detection_list = region.detection_types or []
        if isinstance(detection_list, str):
            import json as _json
            detection_list = _json.loads(detection_list)
        if "flood" in detection_list:
            if sh_client and sh_client != "your-sentinel-hub-client-id":
                try:
                    fetcher = SentinelHubFetcher()
                    before_sar = fetcher.get_sentinel1_composite(bbox, before_start, before_end)
                    after_sar = fetcher.get_sentinel1_composite(bbox, after_start, after_end)
                except Exception as exc:
                    logger.warning("SAR fetch failed for region %d: %s", region_id, exc)
            if before_sar is None:
                from apps.api.services.mock_imagery import MockImageryProvider
                mock_sar = MockImageryProvider(change_type="flood", seed=region_id)
                before_sar = mock_sar.before_sar()
                after_sar = mock_sar.after_sar()

        # Run classifier
        from apps.api.services.classifier import EventClassifier

        det_types = region.detection_types or ["construction", "deforestation", "fire", "solar"]
        if isinstance(det_types, str):
            import json as _json
            det_types = _json.loads(det_types)
        classifier = EventClassifier(detection_types=det_types, bbox=bbox)
        result = classifier.classify(before_s2, after_s2, before_sar, after_sar)

        if result is None:
            logger.info("No significant change detected in region %d", region_id)
            return {"region_id": region_id, "result": "no_change"}

        # Generate tile URLs (use Sentinel Hub thumbnail links as proxy)
        before_tile_url = _tile_url(bbox, before_start, before_end)
        after_tile_url = _tile_url(bbox, after_start, after_end)

        # Persist the event
        event = Event(
            region_id=region_id,
            detected_type=result.detected_type,
            confidence=result.confidence,
            lat=result.lat,
            lon=result.lon,
            before_tile_url=before_tile_url,
            after_tile_url=after_tile_url,
        )
        db.add(event)
        db.commit()
        db.refresh(event)

        logger.info(
            "Event %d created: type=%s confidence=%.3f region=%d",
            event.id, event.detected_type, event.confidence, region_id,
        )

        # Dispatch classification + explanation task
        classify_change.apply_async(args=[event.id], queue="scanning")

        return {
            "region_id": region_id,
            "event_id": event.id,
            "detected_type": result.detected_type,
            "confidence": result.confidence,
        }
    finally:
        db.close()


# ── classify_change ────────────────────────────────────────────────────────────

@app.task(name="apps.worker.tasks.classify_change", bind=True, max_retries=2)
def classify_change(self, event_id: int) -> Dict[str, Any]:
    """
    Enrich an existing Event with an LLM-generated description, then
    dispatch alert notifications to all subscribers of the region.
    """
    db = _get_db_session()
    try:
        from apps.api.models import Event, Region, AlertSubscription
        from apps.api.services.explainer import EventExplainer

        event = db.query(Event).filter(Event.id == event_id).first()
        if not event:
            return {"error": "event_not_found"}

        region = db.query(Region).filter(Region.id == event.region_id).first()

        # Generate description
        explainer = EventExplainer()
        description = explainer.explain(
            {
                "detected_type": event.detected_type,
                "confidence": event.confidence,
                "lat": event.lat,
                "lon": event.lon,
                "region_name": region.name if region else "Unknown",
                "first_seen": event.first_seen.isoformat() if event.first_seen else None,
                "before_date": "the previous observation period",
                "after_date": event.first_seen.strftime("%Y-%m-%d") if event.first_seen else "recently",
            }
        )

        event.description = description
        db.commit()

        # Dispatch alerts to subscribers
        subscriptions = (
            db.query(AlertSubscription)
            .filter(AlertSubscription.region_id == event.region_id)
            .all()
        )

        alert_tasks = []
        for sub in subscriptions:
            send_alert.apply_async(
                args=[event_id, sub.id],
                queue="alerts",
            )
            alert_tasks.append(sub.id)

        return {
            "event_id": event_id,
            "description_set": bool(description),
            "alerts_dispatched": len(alert_tasks),
        }
    finally:
        db.close()


# ── send_alert ─────────────────────────────────────────────────────────────────

@app.task(name="apps.worker.tasks.send_alert", bind=True, max_retries=3,
          default_retry_delay=60)
def send_alert(self, event_id: int, subscription_id: int) -> Dict[str, Any]:
    """
    Send an email and/or Slack notification for a single event to a single
    subscriber.
    """
    db = _get_db_session()
    try:
        from apps.api.models import Event, Region, AlertSubscription
        from apps.api.services.notifier import AlertNotifier

        event = db.query(Event).filter(Event.id == event_id).first()
        sub = db.query(AlertSubscription).filter(AlertSubscription.id == subscription_id).first()

        if not event or not sub:
            return {"error": "event_or_subscription_not_found"}

        region = db.query(Region).filter(Region.id == event.region_id).first()

        event_dict = {
            "id": event.id,
            "region_name": region.name if region else "Unknown",
            "detected_type": event.detected_type,
            "confidence": event.confidence,
            "lat": event.lat,
            "lon": event.lon,
            "first_seen": event.first_seen.isoformat() if event.first_seen else None,
            "description": event.description,
            "before_tile_url": event.before_tile_url,
            "after_tile_url": event.after_tile_url,
        }

        notifier = AlertNotifier()
        results = {}

        if sub.email:
            results["email"] = notifier.send_email(sub.email, event_dict)

        if sub.slack_webhook:
            results["slack"] = notifier.send_slack(sub.slack_webhook, event_dict)

        return {"event_id": event_id, "subscription_id": subscription_id, "results": results}
    finally:
        db.close()


# ── dispatch_pending_alerts ────────────────────────────────────────────────────

@app.task(name="apps.worker.tasks.dispatch_pending_alerts")
def dispatch_pending_alerts() -> Dict[str, Any]:
    """
    Safety-net task: find events created in the last hour that have no
    description yet (classify_change may have failed) and re-enqueue them.
    """
    db = _get_db_session()
    try:
        from apps.api.models import Event

        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=1)
        stale_events = (
            db.query(Event)
            .filter(Event.created_at >= cutoff, Event.description.is_(None))
            .all()
        )

        requeued = []
        for event in stale_events:
            classify_change.apply_async(args=[event.id], queue="scanning")
            requeued.append(event.id)
            logger.info("Re-enqueued classify_change for stale event %d", event.id)

        return {"requeued": requeued}
    finally:
        db.close()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _region_bbox(region) -> Optional[List[float]]:
    """Extract [min_lon, min_lat, max_lon, max_lat] from a Region ORM object."""
    try:
        geom = region.geom
        if hasattr(geom, "desc"):
            from geoalchemy2.shape import to_shape  # type: ignore
            shape = to_shape(geom)
            b = shape.bounds  # (minx, miny, maxx, maxy)
            return [b[0], b[1], b[2], b[3]]
        elif isinstance(geom, str) and geom.startswith(("POLYGON", "SRID")):
            wkt = geom.split(";")[-1] if ";" in geom else geom
            from shapely import wkt as swkt
            shape = swkt.loads(wkt)
            b = shape.bounds
            return [b[0], b[1], b[2], b[3]]
    except Exception as exc:
        logger.error("Could not parse region geometry: %s", exc)
    return None


def _ps_to_s2_compat(ps_array) -> "np.ndarray":
    """
    Map PlanetScope (H,W,4) [B,G,R,NIR] to a 12-band S2-compatible array.

    S2 band layout used by the change detectors:
      idx 1=B02(Blue), 2=B03(Green), 3=B04(Red), 7=B08(NIR)
    Other bands are zeroed — detectors only use the above four.
    """
    import numpy as np

    h, w = ps_array.shape[:2]
    out = np.zeros((h, w, 12), dtype=np.float32)
    out[:, :, 1] = ps_array[:, :, 0]  # Blue  → B02
    out[:, :, 2] = ps_array[:, :, 1]  # Green → B03
    out[:, :, 3] = ps_array[:, :, 2]  # Red   → B04
    out[:, :, 7] = ps_array[:, :, 3]  # NIR   → B08
    return out


def _tile_url(bbox: List[float], start_date: str, end_date: str) -> str:
    """
    Build a Sentinel Hub EO Browser thumbnail URL for display in the UI.
    Uses the public WMS endpoint (no auth required for thumbnails).
    """
    w, s, e, n = bbox
    # Sentinel Hub EO Browser sharing link format
    return (
        f"https://apps.sentinel-hub.com/eo-browser/?"
        f"zoom=12&lat={(s+n)/2:.4f}&lng={(w+e)/2:.4f}"
        f"&themeId=DEFAULT-THEME&datasetId=S2L2A"
        f"&fromTime={start_date}T00%3A00%3A00.000Z"
        f"&toTime={end_date}T23%3A59%3A59.999Z"
        f"&layerId=TRUE-COLOR"
    )
