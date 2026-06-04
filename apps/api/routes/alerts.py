from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from apps.api.database import get_db
from apps.api.models import AlertSubscription, Region
from apps.api.schemas import (
    AlertSubscriptionCreate,
    AlertSubscriptionRead,
    AlertUnsubscribeRequest,
)

router = APIRouter()


@router.post(
    "/subscribe",
    response_model=AlertSubscriptionRead,
    status_code=status.HTTP_201_CREATED,
)
def subscribe(
    payload: AlertSubscriptionCreate,
    db: Session = Depends(get_db),
) -> AlertSubscriptionRead:
    if not payload.email and not payload.slack_webhook:
        raise HTTPException(
            status_code=400,
            detail="At least one of 'email' or 'slack_webhook' must be provided.",
        )

    region = db.query(Region).filter(Region.id == payload.region_id).first()
    if not region:
        raise HTTPException(status_code=404, detail="Region not found")

    # Avoid duplicate subscriptions for the same email+region
    if payload.email:
        existing = (
            db.query(AlertSubscription)
            .filter(
                AlertSubscription.region_id == payload.region_id,
                AlertSubscription.email == payload.email,
            )
            .first()
        )
        if existing:
            return AlertSubscriptionRead.model_validate(existing)

    sub = AlertSubscription(
        region_id=payload.region_id,
        email=payload.email,
        slack_webhook=payload.slack_webhook,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return AlertSubscriptionRead.model_validate(sub)


@router.delete("/unsubscribe", status_code=status.HTTP_204_NO_CONTENT)
def unsubscribe(
    payload: AlertUnsubscribeRequest,
    db: Session = Depends(get_db),
) -> None:
    sub = (
        db.query(AlertSubscription)
        .filter(AlertSubscription.id == payload.subscription_id)
        .first()
    )
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    db.delete(sub)
    db.commit()
