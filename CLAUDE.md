# Sentinel — Autonomous Satellite Anomaly Detection System

## Project Overview

Sentinel monitors user-defined geographic regions using satellite imagery (Sentinel-2 optical, Sentinel-1 SAR) and automatically detects land-use changes: construction, deforestation, fire damage, flooding, and solar farm installation. Detected events are classified, described in plain English via an LLM, and dispatched to subscribers via email/Slack.

## Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI + SQLAlchemy + PostGIS (PostgreSQL) |
| Task Queue | Celery + Redis (broker + result backend) |
| Migrations | Alembic |
| Imagery | Sentinel Hub Process API (OAuth2), Google Earth Engine |
| Change Detection | NumPy + rasterio + scikit-image |
| Classification | PyTorch MobileNetV3-small (fine-tuned per class) |
| LLM Explanation | Groq API – Llama 3.3-70B |
| Notifications | SendGrid (email) + Slack Webhooks |
| Frontend | Vite + React 18 + TypeScript + Tailwind + Leaflet |
| CI/CD | GitHub Actions → Docker Hub → Fly.io |

## Directory Structure

```
sentinel/
├── apps/
│   ├── api/          # FastAPI app + services
│   │   ├── alembic/  # DB migrations
│   │   ├── routes/   # Endpoint routers
│   │   ├── services/ # Business logic
│   │   └── tests/    # Pytest suite
│   ├── worker/       # Celery worker + beat
│   └── web/          # React frontend
├── ml/               # Training scripts
├── models/           # Saved .pt model files
├── notebooks/        # Jupyter exploration
└── scripts/          # Seeding / replay utilities
```

## Run Commands

### Local development (Docker Compose)

```bash
cp .env.example .env          # fill in real credentials
docker compose up --build     # starts api, worker, beat, redis, postgres
```

API: http://localhost:8000
Frontend dev server: `cd apps/web && npm install && npm run dev` → http://localhost:5173

### Database migrations

```bash
docker compose exec api alembic upgrade head
```

### Run tests

```bash
docker compose exec api pytest apps/api/tests/ -v
```

### Train a model

```bash
python ml/train_construction.py --epochs 20 --batch-size 32
python ml/train_solar.py --epochs 20 --batch-size 32
python ml/eval.py --model models/construction_v1.pt --class construction
```

### Seed demo data

```bash
python scripts/seed_demo_regions.py
python scripts/replay_historical.py
```

## Key Architectural Decisions

1. **Celery Beat drives all scanning** — `scan_all_regions` task runs every hour, queries regions with due cadences, dispatches per-region `scan_region` subtasks. This keeps the API stateless.

2. **PostGIS for geometry** — Region polygons stored as PostGIS `GEOMETRY(Polygon, 4326)`. Spatial queries use `ST_Contains` / `ST_Intersects`.

3. **Change detection pipeline** — Each region scan fetches a before/after composite (T-cadence vs T). Difference indices (NDVI, NDBI, NBR, SAR backscatter) are computed per detector. The `EventClassifier` runs all detectors and picks the highest-confidence positive.

4. **Groq Llama for descriptions** — Cheaper and faster than GPT-4 for the 2-3 sentence summaries. Descriptions are stored on the Event row after classification.

5. **Model files are gitignored** — `models/*.pt` are large binaries. CI skips PyTorch inference if no model file is present; services fall back to rule-based logic.

6. **Frontend proxies to API** — Vite dev server proxies `/api` → `http://localhost:8000`. In production, Fly.io routes `/api` to the API machine.

## Environment Variables

See `.env.example` for the full list. Critical ones:

- `DATABASE_URL` — PostgreSQL+PostGIS connection string
- `REDIS_URL` — Redis connection string
- `SENTINEL_HUB_CLIENT_ID` / `SENTINEL_HUB_CLIENT_SECRET` — Sentinel Hub OAuth credentials
- `GROQ_API_KEY` — Groq API key for LLM descriptions
- `SENDGRID_API_KEY` — SendGrid for email alerts
- `SLACK_WEBHOOK_URL` — Default Slack webhook (per-subscription webhooks override this)
