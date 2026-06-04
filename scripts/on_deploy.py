"""
Runs on every Render deploy before uvicorn starts.
Creates tables, seeds regions, populates historical events.
Crash-proof — any failure prints a warning and continues so uvicorn still starts.
"""
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apps.api.database import Base, SessionLocal, engine
from apps.api.models import Event, Region

# ── 1. Enable PostGIS and create tables ─────────────────────────────────────
try:
    db_url = os.environ.get("DATABASE_URL", "")
    if db_url.startswith("postgresql"):
        with engine.connect() as conn:
            conn.execute(__import__("sqlalchemy").text("CREATE EXTENSION IF NOT EXISTS postgis"))
            conn.commit()
        print("[on_deploy] PostGIS extension ensured.")
    Base.metadata.create_all(bind=engine)
    print("[on_deploy] Tables created.")
except Exception as e:
    print(f"[on_deploy] WARNING: table creation issue: {e}")

# ── 2. Seed regions ──────────────────────────────────────────────────────────
def _wkt(coords):
    pts = ", ".join(f"{lon} {lat}" for lon, lat in coords)
    return f"POLYGON(({pts}))"

REGIONS = [
    ("Tumkur Solar Corridor",  [[76.9,13.2],[77.4,13.2],[77.4,13.7],[76.9,13.7],[76.9,13.2]], ["solar","construction"]),
    ("Bellary Iron Ore Belt",  [[76.7,14.8],[77.2,14.8],[77.2,15.3],[76.7,15.3],[76.7,14.8]], ["construction","deforestation","fire"]),
    ("Sundarbans Delta",       [[88.3,21.5],[89.0,21.5],[89.0,22.1],[88.3,22.1],[88.3,21.5]], ["deforestation","flood"]),
    ("Bhuj Rann of Kutch",     [[69.5,23.2],[70.2,23.2],[70.2,23.7],[69.5,23.7],[69.5,23.2]], ["construction","flood"]),
    ("Chilika Lake Catchment", [[85.1,19.6],[85.6,19.6],[85.6,20.0],[85.1,20.0],[85.1,19.6]], ["flood","deforestation","construction"]),
]

try:
    db = SessionLocal()
    if db.query(Region).count() == 0:
        for name, coords, types in REGIONS:
            db.add(Region(
                name=name,
                geom=f"SRID=4326;{_wkt(coords)}",
                detection_types=types,
                cadence=24,
            ))
        db.commit()
        print(f"[on_deploy] Seeded {len(REGIONS)} regions.")
    else:
        print(f"[on_deploy] {db.query(Region).count()} regions already present.")
    db.close()
except Exception as e:
    print(f"[on_deploy] WARNING: region seed failed: {e}")

# ── 3. Replay 6 months of synthetic events ───────────────────────────────────
REGION_EVENTS = {
    "Tumkur Solar Corridor":  [("solar",.4),("construction",.4),("fire",.1),("deforestation",.1)],
    "Bellary Iron Ore Belt":  [("construction",.5),("deforestation",.3),("fire",.2)],
    "Sundarbans Delta":       [("deforestation",.55),("flood",.45)],
    "Bhuj Rann of Kutch":     [("construction",.6),("flood",.4)],
    "Chilika Lake Catchment": [("flood",.5),("deforestation",.3),("construction",.2)],
}
CENTERS = {
    "Tumkur Solar Corridor":(13.45,77.15),"Bellary Iron Ore Belt":(15.05,76.95),
    "Sundarbans Delta":(21.80,88.65),"Bhuj Rann of Kutch":(23.45,69.85),
    "Chilika Lake Catchment":(19.80,85.35),
}
DESCS = {
    "solar":["Photovoltaic panel arrays detected — high SWIR, suppressed NDVI confirm solar farm expansion.",
             "New solar installation visible across ~40 ha. Spectral signature consistent with PV panels."],
    "construction":["Bare soil exposure and NDBI increase indicate active construction or land clearing.",
                    "New impervious surfaces detected. Pattern consistent with industrial development."],
    "deforestation":["Sharp NDVI decline in forested area — consistent with planned agricultural clearing.",
                     "Forest cover dropped >40% vs baseline. Change boundary geometrically regular."],
    "fire":["dNBR indicates moderate-high burn severity. VIIRS thermal data confirms fire activity.",
            "Burn scarring visible in NIR/SWIR composite across ~200 ha."],
    "flood":["SAR VV backscatter drop in low-lying areas indicates surface water inundation.",
             "Flood extent expanded ~35% beyond pre-monsoon baseline, affecting agricultural land."],
}

try:
    db = SessionLocal()
    if db.query(Event).count() == 0:
        now = datetime.now(tz=timezone.utc)
        total = 0
        for region in db.query(Region).all():
            weights_list = REGION_EVENTS.get(region.name, [("construction",1.0)])
            center = CENTERS.get(region.name, (20.0, 78.0))
            n = random.randint(10, 20)
            for i in range(n):
                types, weights = zip(*weights_list)
                det = random.choices(list(types), weights=list(weights), k=1)[0]
                dt = (now - timedelta(days=180)) + timedelta(days=i*(180/n) + random.uniform(-5,5))
                if dt > now: dt = now - timedelta(hours=2)
                lat = round(center[0] + random.uniform(-0.18, 0.18), 5)
                lon = round(center[1] + random.uniform(-0.18, 0.18), 5)
                date_str = dt.strftime("%Y-%m-%d")
                before_date = (dt - timedelta(days=21)).strftime("%Y-%m-%d")
                tile = (f"https://apps.sentinel-hub.com/eo-browser/?zoom=13"
                        f"&lat={lat}&lng={lon}&themeId=DEFAULT-THEME&datasetId=S2L2A"
                        f"&fromTime={before_date}T00%3A00%3A00.000Z"
                        f"&toTime={date_str}T23%3A59%3A59.999Z&layerId=TRUE-COLOR")
                db.add(Event(
                    region_id=region.id, detected_type=det,
                    confidence=round(random.uniform(0.38, 0.96), 3),
                    lat=lat, lon=lon,
                    first_seen=dt.replace(tzinfo=None),
                    description=random.choice(DESCS.get(det, ["Change detected."])),
                    before_tile_url=tile, after_tile_url=tile,
                    created_at=dt.replace(tzinfo=None),
                ))
                total += 1
            db.commit()
        print(f"[on_deploy] Replayed {total} historical events.")
    else:
        print(f"[on_deploy] {db.query(Event).count()} events already present.")
    db.close()
except Exception as e:
    print(f"[on_deploy] WARNING: event replay failed: {e}")

print("[on_deploy] Done — starting uvicorn.")
