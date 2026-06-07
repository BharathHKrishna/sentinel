"""
Runs on every Render deploy before uvicorn starts.
Enables PostGIS and creates tables only — no demo data seeding.
Crash-proof — any failure prints a warning and continues so uvicorn still starts.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apps.api.database import Base, SessionLocal, engine
from apps.api.models import Event, Region  # noqa: F401 — ensures models are registered

# ── Enable PostGIS and create tables ────────────────────────────────────────
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

print("[on_deploy] Done — starting uvicorn.")
