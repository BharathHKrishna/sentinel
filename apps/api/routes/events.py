from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from apps.api.database import get_db
from apps.api.models import Event
from apps.api.schemas import EventRead, EventFeedbackRequest

router = APIRouter()


@router.get("/", response_model=List[EventRead])
def list_events(
    region_id: Optional[int] = Query(None, description="Filter by region ID"),
    detected_type: Optional[str] = Query(None, description="Filter by detection type"),
    since: Optional[datetime] = Query(None, description="Only events after this ISO datetime"),
    until: Optional[datetime] = Query(None, description="Only events before this ISO datetime"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> List[EventRead]:
    q = db.query(Event)

    if region_id is not None:
        q = q.filter(Event.region_id == region_id)

    if detected_type is not None:
        q = q.filter(Event.detected_type == detected_type)

    if since is not None:
        q = q.filter(Event.first_seen >= since)

    if until is not None:
        q = q.filter(Event.first_seen <= until)

    events = (
        q.order_by(Event.first_seen.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [EventRead.model_validate(e) for e in events]


@router.get("/{event_id}", response_model=EventRead)
def get_event(event_id: int, db: Session = Depends(get_db)) -> EventRead:
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return EventRead.model_validate(event)


@router.patch("/{event_id}/feedback", response_model=EventRead)
def submit_feedback(
    event_id: int,
    payload: EventFeedbackRequest,
    db: Session = Depends(get_db),
) -> EventRead:
    """Mark an event as a false positive (or confirm it). Used for precision tracking."""
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    event.is_false_positive = payload.is_false_positive
    db.commit()
    db.refresh(event)
    return EventRead.model_validate(event)
