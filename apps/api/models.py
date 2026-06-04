from datetime import datetime
from typing import List

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Integer,
    String,
    Float,
    Text,
    DateTime,
    ForeignKey,
    func,
)
from sqlalchemy.orm import relationship

from apps.api.database import Base

import os as _os
_DB_URL = _os.environ.get("DATABASE_URL", "")
_USE_POSTGIS = _DB_URL.startswith("postgresql") and __import__("importlib.util", fromlist=["find_spec"]).find_spec("geoalchemy2") is not None

if _USE_POSTGIS:
    from geoalchemy2 import Geometry  # type: ignore


class Region(Base):
    __tablename__ = "regions"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)

    if _USE_POSTGIS:
        geom = Column(Geometry(geometry_type="POLYGON", srid=4326), nullable=False)
    else:
        geom = Column(Text, nullable=False)  # WKT stored as "SRID=4326;POLYGON(...)"

    detection_types = Column(JSON, nullable=False, default=list)
    cadence = Column(Integer, nullable=False, default=24)  # hours between scans
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    owner_email = Column(String(255), nullable=True)

    events: List["Event"] = relationship(
        "Event", back_populates="region", cascade="all, delete-orphan"
    )
    subscriptions: List["AlertSubscription"] = relationship(
        "AlertSubscription", back_populates="region", cascade="all, delete-orphan"
    )


class Event(Base):
    __tablename__ = "events"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)
    region_id = Column(Integer, ForeignKey("regions.id", ondelete="CASCADE"), nullable=False, index=True)
    detected_type = Column(String(100), nullable=False, index=True)
    confidence = Column(Float, nullable=False)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    first_seen = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    description = Column(Text, nullable=True)
    before_tile_url = Column(Text, nullable=True)
    after_tile_url = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_false_positive = Column(Boolean, nullable=True, default=None, index=True)

    region: "Region" = relationship("Region", back_populates="events")


class AlertSubscription(Base):
    __tablename__ = "alert_subscriptions"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)
    region_id = Column(Integer, ForeignKey("regions.id", ondelete="CASCADE"), nullable=False, index=True)
    email = Column(String(255), nullable=True)
    slack_webhook = Column(Text, nullable=True)

    region: "Region" = relationship("Region", back_populates="subscriptions")
