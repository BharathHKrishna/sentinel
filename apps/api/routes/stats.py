from datetime import datetime, timedelta, timezone
from typing import Dict, Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from apps.api.database import get_db
from apps.api.models import Region, Event, AlertSubscription

router = APIRouter()


@router.get("/", response_model=Dict[str, Any])
def get_stats(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Aggregate stats for the dashboard header counters."""
    total_regions = db.query(func.count(Region.id)).scalar() or 0
    total_events = db.query(func.count(Event.id)).scalar() or 0
    total_subscriptions = db.query(func.count(AlertSubscription.id)).scalar() or 0

    since_7d = datetime.now(tz=timezone.utc) - timedelta(days=7)
    since_30d = datetime.now(tz=timezone.utc) - timedelta(days=30)

    events_7d = (
        db.query(func.count(Event.id))
        .filter(Event.first_seen >= since_7d)
        .scalar() or 0
    )
    events_30d = (
        db.query(func.count(Event.id))
        .filter(Event.first_seen >= since_30d)
        .scalar() or 0
    )

    # Count by type (all time)
    type_rows = (
        db.query(Event.detected_type, func.count(Event.id))
        .group_by(Event.detected_type)
        .all()
    )
    events_by_type = {row[0]: row[1] for row in type_rows}

    # Count by type in last 7 days
    type_rows_7d = (
        db.query(Event.detected_type, func.count(Event.id))
        .filter(Event.first_seen >= since_7d)
        .group_by(Event.detected_type)
        .all()
    )
    events_by_type_7d = {row[0]: row[1] for row in type_rows_7d}

    # Confirmed (not false-positive) events
    confirmed = (
        db.query(func.count(Event.id))
        .filter(Event.is_false_positive.is_(False))
        .scalar() or 0
    )

    return {
        "total_regions": total_regions,
        "total_events": total_events,
        "total_subscriptions": total_subscriptions,
        "events_7d": events_7d,
        "events_30d": events_30d,
        "events_by_type": events_by_type,
        "events_by_type_7d": events_by_type_7d,
        "confirmed_events": confirmed,
    }
