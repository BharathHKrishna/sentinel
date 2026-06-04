"""
Runs once on every Render deploy (called from startCommand via &&).
Creates tables and seeds demo data if the DB is empty.
Safe to run repeatedly — idempotent.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apps.api.database import Base, SessionLocal, engine
from apps.api.models import Region, Event
from apps.api.routes.regions import _geom_to_wkt

Base.metadata.create_all(bind=engine)
print("[on_deploy] Tables ensured.")

db = SessionLocal()
try:
    if db.query(Region).count() == 0:
        regions = [
            ("Tumkur Solar Corridor",  [[76.9,13.2],[77.4,13.2],[77.4,13.7],[76.9,13.7],[76.9,13.2]], ["solar","construction"]),
            ("Bellary Iron Ore Belt",  [[76.7,14.8],[77.2,14.8],[77.2,15.3],[76.7,15.3],[76.7,14.8]], ["construction","deforestation","fire"]),
            ("Sundarbans Delta",       [[88.3,21.5],[89.0,21.5],[89.0,22.1],[88.3,22.1],[88.3,21.5]], ["deforestation","flood"]),
            ("Bhuj Rann of Kutch",     [[69.5,23.2],[70.2,23.2],[70.2,23.7],[69.5,23.7],[69.5,23.2]], ["construction","flood"]),
            ("Chilika Lake Catchment", [[85.1,19.6],[85.6,19.6],[85.6,20.0],[85.1,20.0],[85.1,19.6]], ["flood","deforestation","construction"]),
        ]
        for name, coords, types in regions:
            geom = {"type": "Polygon", "coordinates": [coords]}
            wkt = _geom_to_wkt(geom)
            db.add(Region(name=name, geom=f"SRID=4326;{wkt}", detection_types=types, cadence=24))
        db.commit()
        print(f"[on_deploy] Seeded {len(regions)} regions.")

    if db.query(Event).count() == 0:
        # Run replay to populate historical events
        import subprocess
        subprocess.run([sys.executable, "scripts/replay_historical.py"], check=True)
        print("[on_deploy] Historical events replayed.")
    else:
        print(f"[on_deploy] {db.query(Event).count()} events already present.")
finally:
    db.close()

print("[on_deploy] Done.")
