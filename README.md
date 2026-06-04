# Sentinel — Autonomous Satellite Anomaly Detection

> Point it at a region. Every cycle, it fetches new satellite imagery, detects what changed, and sends you an alert with an AI-written explanation.

[![CI](https://github.com/yourname/sentinel/actions/workflows/ci.yml/badge.svg)](https://github.com/yourname/sentinel/actions)

## What it does

Sentinel monitors user-defined geographic regions using Sentinel-1/2 satellite imagery and Planet Labs PlanetScope. When it detects a significant land-use change — new construction, deforestation, fires, flooding, or solar farm installation — it:

1. Classifies the event type and computes a confidence score
2. Generates a plain-English explanation using Llama 3.3-70B (Groq)
3. Dispatches an email or Slack alert to subscribers
4. Logs everything to a public event feed with before/after imagery tiles

## Quick start

```bash
cp .env.example .env          # fill in PLANET_API_KEY + optional GROQ_API_KEY
make up                       # starts api, worker, beat, redis, postgres
make migrate                  # run DB migrations
make seed                     # insert 5 demo regions (Tumkur, Bellary, Sundarbans…)
make web                      # start Vite dev server → http://localhost:5173
```

Trigger a manual scan (no need to wait for the scheduler):
```bash
make scan-all
# or for a specific region:
make scan-region              # prompts for region ID
```

## Architecture

```
┌─────────────────────────────────────────────────┐
│                    React + Leaflet               │  ← http://localhost:5173
│           Dashboard / RegionEditor / EventFeed   │
└────────────────────┬────────────────────────────┘
                     │ REST
┌────────────────────▼────────────────────────────┐
│              FastAPI  (port 8000)                │
│  /api/regions   /api/events   /api/alerts        │
│  /api/stats     /api/admin                       │
│                  PostGIS (PostgreSQL)             │
└──────────────┬──────────────────────────────────┘
               │ Celery tasks via Redis
┌──────────────▼──────────────────────────────────┐
│              Celery Worker + Beat                │
│                                                  │
│  scan_region()                                   │
│    ├─ PlanetFetcher  (3 m PlanetScope, primary)  │
│    ├─ SentinelHubFetcher  (10 m S2, fallback)    │
│    ├─ GenericChangeDetector  (NDVI/NDBI/NDWI)    │
│    ├─ ConstructionDetector  (NDBI + GLCM)        │
│    ├─ DeforestationDetector (NDVI decline)       │
│    ├─ FireDetector  (dNBR + VIIRS cross-check)   │
│    ├─ FloodDetector  (S1 SAR backscatter)        │
│    └─ SolarDetector  (CNN or NDBI+NDVI rules)   │
│                                                  │
│  classify_change()  →  Groq LLM explanation      │
│  send_alert()       →  SendGrid + Slack          │
└──────────────────────────────────────────────────┘
```

## Detection methods

| Type | Primary signal | Secondary |
|------|---------------|-----------|
| Construction | NDBI delta + GLCM texture | — |
| Deforestation | NDVI decline in forested areas | — |
| Fire | dNBR (Normalised Burn Ratio) | VIIRS active fire API |
| Flood | Sentinel-1 VV backscatter decrease | Urban mask from NDBI |
| Solar farm | CNN (MobileNetV3-small) | NDBI+NDVI rule fallback |

## Stack

| Layer | Tech |
|-------|------|
| Imagery | Planet Labs PlanetScope (3 m) · Sentinel Hub S2/S1 (10 m) |
| Change detection | NumPy · rasterio · scikit-image |
| Classification | PyTorch MobileNetV3-small (fine-tuned) |
| LLM | Groq API — Llama 3.3-70B |
| Scheduling | Celery Beat + Redis |
| API | FastAPI + SQLAlchemy + PostGIS |
| Frontend | Vite + React 18 + TypeScript + Tailwind + Leaflet |
| Alerts | SendGrid (email) · Slack Incoming Webhooks |
| CI/CD | GitHub Actions → Docker Hub → Fly.io |
| Experiment tracking | Weights & Biases |

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `PLANET_API_KEY` | Yes | Planet Labs API key |
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `REDIS_URL` | Yes | Redis connection string |
| `GROQ_API_KEY` | Optional | Enables LLM explanations |
| `SENDGRID_API_KEY` | Optional | Enables email alerts |
| `SLACK_WEBHOOK_URL` | Optional | Enables Slack alerts |
| `SENTINEL_HUB_CLIENT_ID` | Optional | S2/S1 fallback imagery |
| `SENTINEL_HUB_CLIENT_SECRET` | Optional | S2/S1 fallback imagery |
| `NASA_FIRMS_MAP_KEY` | Optional | VIIRS fire cross-check |

## Training the classifiers

```bash
# Label patches first: ml/data/construction/{positive,negative}/
make train-construction   # fine-tunes MobileNetV3-small, logs to W&B
make train-solar          # same for solar farm detector
make eval-models          # prints precision/recall/F1 for both
```

## What it's not

- Not a production-grade alerting system
- Not a substitute for ground-truth verification
- Not trained on enough labels to be commercially deployable

It is a working demonstration of the architecture that underpins commercial systems from LiveEO, AiDash, and constellr.

## Demo regions

Five real Indian regions are seeded by default:

| Region | Detection types | Why interesting |
|--------|----------------|-----------------|
| Tumkur Solar Corridor, Karnataka | solar, construction | Major solar park zone |
| Bellary Iron Ore Belt, Karnataka | construction, deforestation, fire | Active mining region |
| Sundarbans Delta, West Bengal | deforestation, flood | UNESCO mangrove site |
| Bhuj Rann of Kutch, Gujarat | construction, flood | Post-earthquake rebuilding |
| Chilika Lake Catchment, Odisha | flood, deforestation, construction | Largest coastal lagoon in India |
