from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, field_validator


# ── Region ─────────────────────────────────────────────────────────────────────

class RegionCreate(BaseModel):
    name: str
    lat: float   # center point latitude
    lon: float   # center point longitude — backend expands to 1024m bbox
    detection_types: List[str] = []
    cadence: int = 24  # hours
    owner_email: Optional[str] = None

    @field_validator("lat")
    @classmethod
    def validate_lat(cls, v: float) -> float:
        if not -90 <= v <= 90:
            raise ValueError("lat must be between -90 and 90")
        return v

    @field_validator("lon")
    @classmethod
    def validate_lon(cls, v: float) -> float:
        if not -180 <= v <= 180:
            raise ValueError("lon must be between -180 and 180")
        return v

    @field_validator("detection_types")
    @classmethod
    def validate_detection_types(cls, v: List[str]) -> List[str]:
        allowed = {"construction", "deforestation", "fire", "flood", "solar"}
        for t in v:
            if t not in allowed:
                raise ValueError(f"Unknown detection type: {t}. Allowed: {allowed}")
        return v

    @field_validator("cadence")
    @classmethod
    def validate_cadence(cls, v: int) -> int:
        if v < 1:
            raise ValueError("cadence must be >= 1 hour")
        return v


class RegionRead(BaseModel):
    id: int
    name: str
    geom: Dict[str, Any]
    detection_types: List[str]
    cadence: int
    created_at: datetime
    owner_email: Optional[str] = None

    model_config = {"from_attributes": True}


# ── Event ──────────────────────────────────────────────────────────────────────

class EventRead(BaseModel):
    id: int
    region_id: int
    detected_type: str
    confidence: float
    lat: Optional[float] = None
    lon: Optional[float] = None
    first_seen: datetime
    description: Optional[str] = None
    before_tile_url: Optional[str] = None
    after_tile_url: Optional[str] = None
    created_at: datetime
    is_false_positive: Optional[bool] = None

    model_config = {"from_attributes": True}


class EventFeedbackRequest(BaseModel):
    is_false_positive: bool


class EventCreate(BaseModel):
    region_id: int
    detected_type: str
    confidence: float
    lat: Optional[float] = None
    lon: Optional[float] = None
    description: Optional[str] = None
    before_tile_url: Optional[str] = None
    after_tile_url: Optional[str] = None


# ── AlertSubscription ──────────────────────────────────────────────────────────

class AlertSubscriptionCreate(BaseModel):
    region_id: int
    email: Optional[str] = None
    slack_webhook: Optional[str] = None

    @field_validator("email", "slack_webhook", mode="before")
    @classmethod
    def at_least_one_channel(cls, v: Optional[str]) -> Optional[str]:
        return v  # cross-field check done in route


class AlertSubscriptionRead(BaseModel):
    id: int
    region_id: int
    email: Optional[str] = None
    slack_webhook: Optional[str] = None

    model_config = {"from_attributes": True}


class AlertUnsubscribeRequest(BaseModel):
    subscription_id: int
