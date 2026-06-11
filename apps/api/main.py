import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from apps.api.database import Base, engine
from apps.api.routes import regions, events, alerts, stats, admin


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Create tables on startup (idempotent — alembic handles migrations in prod)
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Sentinel API",
    description="Autonomous satellite anomaly detection for monitored regions",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow the Vite dev server and any configured frontend origin
origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173"),
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(regions.router, prefix="/api/regions", tags=["regions"])
app.include_router(events.router, prefix="/api/events", tags=["events"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"])
app.include_router(stats.router, prefix="/api/stats", tags=["stats"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])


@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {"status": "ok", "service": "sentinel-api"}


@app.get("/debug/scan-test", tags=["meta"])
async def scan_test() -> dict:
    """Test scan imports and return any errors."""
    results = {}
    try:
        from apps.api.services.imagery import FreeS2Fetcher
        results["imagery_import"] = "ok"
    except Exception as e:
        results["imagery_import"] = str(e)
    try:
        from apps.worker.tasks import _region_bbox, _tile_url, _ps_to_s2_compat
        results["tasks_import"] = "ok"
    except Exception as e:
        results["tasks_import"] = str(e)
    try:
        from apps.api.services.classifier import EventClassifier
        results["classifier_import"] = "ok"
    except Exception as e:
        results["classifier_import"] = str(e)
    try:
        from apps.api.services.explainer import EventExplainer
        results["explainer_import"] = "ok"
    except Exception as e:
        results["explainer_import"] = str(e)
    return results
