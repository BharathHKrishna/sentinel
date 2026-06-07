from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from apps.api.database import get_db
from apps.api.models import Region
from apps.api.schemas import RegionCreate, RegionRead

router = APIRouter()


def _geom_to_wkt(geom: dict) -> str:
    if geom.get("type") != "Polygon":
        raise ValueError("Only Polygon geometry is supported")
    rings = geom["coordinates"]
    ring_strs = []
    for ring in rings:
        pts = ", ".join(f"{lon} {lat}" for lon, lat in ring)
        ring_strs.append(f"({pts})")
    return f"POLYGON({', '.join(ring_strs)})"


def _region_to_read(region: Region) -> RegionRead:
    import shapely.geometry as sg
    geom_val = region.geom
    if hasattr(geom_val, "desc"):
        from geoalchemy2.shape import to_shape  # type: ignore
        shape = to_shape(geom_val)
        geom_dict = sg.mapping(shape)
    elif isinstance(geom_val, str):
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
    try:
        wkt = _geom_to_wkt(payload.geom)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

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
