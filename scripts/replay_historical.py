"""
Populate 6 months of synthetic historical events for demo regions.

Inserts directly via SQLAlchemy ORM — works with both PostgreSQL and SQLite.
Run after init_dev.py / seed_demo_regions.py.

Usage:
    PYTHONPATH=. DATABASE_URL=sqlite:///./sentinel_dev.db python scripts/replay_historical.py
    PYTHONPATH=. DATABASE_URL=sqlite:///./sentinel_dev.db python scripts/replay_historical.py --clear
"""
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apps.api.database import SessionLocal
from apps.api.models import Event, Region

REGION_EVENT_MAP = {
    "Tumkur Solar Corridor":  [("solar", 0.40), ("construction", 0.40), ("fire", 0.10), ("deforestation", 0.10)],
    "Bellary Iron Ore Belt":  [("construction", 0.50), ("deforestation", 0.30), ("fire", 0.20)],
    "Sundarbans Delta":       [("deforestation", 0.55), ("flood", 0.45)],
    "Bhuj Rann of Kutch":     [("construction", 0.60), ("flood", 0.40)],
    "Chilika Lake Catchment": [("flood", 0.50), ("deforestation", 0.30), ("construction", 0.20)],
}

REGION_CENTERS = {
    "Tumkur Solar Corridor":  (13.45, 77.15),
    "Bellary Iron Ore Belt":  (15.05, 76.95),
    "Sundarbans Delta":       (21.80, 88.65),
    "Bhuj Rann of Kutch":     (23.45, 69.85),
    "Chilika Lake Catchment": (19.80, 85.35),
}

DESCRIPTIONS = {
    "solar": [
        "A large-scale photovoltaic installation was detected, consistent with utility-scale solar farm development. Panel rows are visible in the NIR/SWIR composite with characteristic low NDVI and elevated NDBI.",
        "New rows of solar panels are visible across approximately 40 hectares. The spectral signature — high SWIR reflectance and near-zero vegetation index — confirms photovoltaic installation.",
        "High reflectance from panel arrays and suppressed NDVI confirm a solar farm expansion. The installation appears to have displaced previously fallow agricultural land.",
    ],
    "construction": [
        "Significant bare soil exposure and increased built-up index indicate active construction or land clearing. Road networks and levelled ground are consistent with industrial or residential development.",
        "New impervious surfaces are visible in the SWIR composite, with texture analysis indicating recently disturbed land. The pattern is consistent with warehouse or factory construction.",
        "GLCM texture analysis and NDBI delta point to new construction activity spanning approximately 3–5 hectares along the existing infrastructure corridor.",
    ],
    "deforestation": [
        "A sharp NDVI decline across a previously forested patch suggests large-scale clearing. The change boundary is geometrically regular, indicating planned agricultural or industrial activity.",
        "Forest loss is visible along the patch boundary, consistent with agricultural encroachment. Vegetation cover dropped by over 40% compared to the baseline period.",
        "Vegetation cover dropped sharply between composites. The spectral change is confined to approximately 80 hectares previously covered by dense canopy.",
    ],
    "fire": [
        "Burn scarring is visible in the NIR/SWIR composite, with dNBR values indicating moderate-to-high burn severity across approximately 200 hectares.",
        "Active fire signatures were cross-referenced against VIIRS thermal data, confirming a significant burning event. Post-fire charred surface reflectance is clearly visible.",
        "Post-fire vegetation loss and charred surface reflectance confirm recent burning activity. The burn scar follows topographic contours consistent with wildfire spread.",
    ],
    "flood": [
        "SAR backscatter decreased significantly in low-lying areas adjacent to the water body, consistent with surface water inundation extending 2–4 km beyond the normal shoreline.",
        "Open-water reflectance and VV backscatter drop indicate flooding of low-lying agricultural land. Flood extent exceeds the pre-monsoon baseline by approximately 35%.",
        "Flood extent expanded compared to the pre-monsoon baseline, affecting agricultural fields and road access. The inundation pattern follows drainage channels and low-gradient terrain.",
    ],
}


def _tile_url(lat: float, lon: float, date: str, window_days: int = 7) -> str:
    from_date = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=window_days)).strftime("%Y-%m-%d")
    return (
        f"https://apps.sentinel-hub.com/eo-browser/?zoom=13"
        f"&lat={lat:.4f}&lng={lon:.4f}&themeId=DEFAULT-THEME&datasetId=S2L2A"
        f"&fromTime={from_date}T00%3A00%3A00.000Z"
        f"&toTime={date}T23%3A59%3A59.999Z"
        f"&layerId=TRUE-COLOR"
    )


def generate_and_insert(clear_existing: bool = False) -> int:
    db = SessionLocal()
    try:
        if clear_existing:
            db.query(Event).delete()
            db.commit()
            print("Cleared existing events.")

        existing = db.query(Event).count()
        if existing > 0 and not clear_existing:
            print(f"Already have {existing} events — skipping. Pass --clear to regenerate.")
            return existing

        regions = db.query(Region).all()
        if not regions:
            print("No regions found. Run init_dev.py first.")
            sys.exit(1)

        print(f"Generating 6 months of events for {len(regions)} regions...\n")
        now = datetime.now(tz=timezone.utc)
        six_months_ago = now - timedelta(days=180)
        total = 0

        for region in regions:
            name = region.name
            event_weights = REGION_EVENT_MAP.get(name, [("construction", 1.0)])
            center = REGION_CENTERS.get(name, (20.0, 78.0))
            n_events = random.randint(10, 20)
            interval_days = 180 / n_events

            for i in range(n_events):
                types, weights = zip(*event_weights)
                det_type = random.choices(list(types), weights=list(weights), k=1)[0]

                jitter = random.uniform(-interval_days * 0.3, interval_days * 0.3)
                first_seen_dt = six_months_ago + timedelta(days=i * interval_days + jitter)
                if first_seen_dt > now:
                    first_seen_dt = now - timedelta(hours=random.randint(1, 48))

                lat = round(center[0] + random.uniform(-0.18, 0.18), 5)
                lon = round(center[1] + random.uniform(-0.18, 0.18), 5)
                confidence = round(random.uniform(0.38, 0.96), 3)
                description = random.choice(DESCRIPTIONS.get(det_type, ["Change detected."]))

                date_str = first_seen_dt.strftime("%Y-%m-%d")
                before_date = (first_seen_dt - timedelta(days=21)).strftime("%Y-%m-%d")

                db.add(Event(
                    region_id=region.id,
                    detected_type=det_type,
                    confidence=confidence,
                    lat=lat,
                    lon=lon,
                    first_seen=first_seen_dt.replace(tzinfo=None),
                    description=description,
                    before_tile_url=_tile_url(lat, lon, before_date),
                    after_tile_url=_tile_url(lat, lon, date_str),
                    created_at=first_seen_dt.replace(tzinfo=None),
                    is_false_positive=None,
                ))
                total += 1

            db.commit()
            print(f"  {name}: {n_events} events")

        print(f"\nTotal: {total} events across {len(regions)} regions.")
        return total

    finally:
        db.close()


if __name__ == "__main__":
    generate_and_insert(clear_existing="--clear" in sys.argv)
