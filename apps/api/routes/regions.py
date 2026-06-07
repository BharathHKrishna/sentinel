import math
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from apps.api.database import get_db
from apps.api.models import Region
from apps.api.schemas import RegionCreate, RegionRead

router = APIRouter()


def _bbox_wkt(lat: float, lon: float, half_m: float = 512.0) -> str:
    """Build a WKT polygon that is a 1024m × 1024m box centred on lat/lon."""
    lat_delta = half_m / 111_320.0
    lon_delta = half_m / (111_320.0 * math.cos(math.radians(lat)))
    w, e = lon - lon_delta, lon + lon_delta
    s, n = lat - lat_delta, lat + lat_delta
    return f"POLYGON(({w} {s}, {e} {s}, {e} {n}, {w} {n}, {w} {s}))"


def _region_to_read(region: Region) -> RegionRead:
    """Serialize a Region ORM object to RegionRead schema."""
    # geom is stored as WKT or GeoAlchemy2 WKBElement — convert to GeoJSON dict
    import shapely.geometry as sg
    geom_val = region.geom
    if hasattr(geom_val, "desc"):
        # GeoAlchemy2 WKBElement (PostGIS)
        from geoalchemy2.shape import to_shape  # type: ignore
        shape = to_shape(geom_val)
        geom_dict = sg.mapping(shape)
    elif isinstance(geom_val, str):
        # WKT string (SQLite): may be prefixed "SRID=4326;POLYGON(...)"
        wkt_str = geom_val.split(";")[-1] if ";" in geom_val else geom_val
        from shapely import wkt as swkt
        shape = swkt.loads(wkt_str)
        geom_dict = sg.mapping(shape)
    else:
        geom_dict = {"type": "Polygon", "coordinates": []}

    dt = region.detection_types or []
    if isinstance(dt, str):
        import json as _json
        try:
            dt = _json.loads(dt)
        except Exception:
            dt = []

    return RegionRead(
        id=region.id,
        name=region.name,
        geom=geom_dict,
        detection_types=dt,
        cadence=region.cadence,
        created_at=region.created_at,
        owner_email=region.owner_email,
    )


@router.post("/", response_model=RegionRead, status_code=status.HTTP_201_CREATED)
def create_region(payload: RegionCreate, db: Session = Depends(get_db)) -> RegionRead:
    wkt = _bbox_wkt(payload.lat, payload.lon)
    region = Region(
        name=payload.name,
        geom=f"SRID=4326;{wkt}",
        detection_types=payload.detection_types,
        cadence=payload.cadence,
        owner_email=payload.owner_email,
    )
    db.add(region)
    db.commit()
    db.refresh(region)
    return _region_to_read(region)


@router.get("/", response_model=List[RegionRead])
def list_regions(db: Session = Depends(get_db)) -> List[RegionRead]:
    regions = db.query(Region).order_by(Region.created_at.desc()).all()
    return [_region_to_read(r) for r in regions]


@router.get("/{region_id}", response_model=RegionRead)
def get_region(region_id: int, db: Session = Depends(get_db)) -> RegionRead:
    region = db.query(Region).filter(Region.id == region_id).first()
    if not region:
        raise HTTPException(status_code=404, detail="Region not found")
    return _region_to_read(region)


@router.delete("/{region_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_region(region_id: int, db: Session = Depends(get_db)) -> None:
    region = db.query(Region).filter(Region.id == region_id).first()
    if not region:
        raise HTTPException(status_code=404, detail="Region not found")
    db.delete(region)
    db.commit()
