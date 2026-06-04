#!/usr/bin/env bash
set -e
PROJ="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJ"

export DATABASE_URL="sqlite:///$PROJ/sentinel_dev.db"
export REDIS_URL="redis://localhost:6379/0"
export PLANET_API_KEY="PLAK8c6cefa60c15455eb86fcc6e3e248a70"
export GROQ_API_KEY="${GROQ_API_KEY:-}"
export SENDGRID_API_KEY="${SENDGRID_API_KEY:-}"
export SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL:-}"
export SENTINEL_HUB_CLIENT_ID="${SENTINEL_HUB_CLIENT_ID:-}"
export SENTINEL_HUB_CLIENT_SECRET="${SENTINEL_HUB_CLIENT_SECRET:-}"
export SECRET_KEY="local-dev-secret"
export PYTHONPATH="$PROJ"

API_PORT=8010
WEB_PORT=5173

echo ""
echo "========================================="
echo "  Sentinel — local dev"
echo "  DB : $PROJ/sentinel_dev.db"
echo "  API: http://localhost:$API_PORT"
echo "  Web: http://localhost:$WEB_PORT"
echo "========================================="
echo ""

# ── 1. Create tables + seed regions ────────────────────────────────────────
echo "[1/4] Initialising DB and seeding demo regions..."
python3 "$PROJ/scripts/init_dev.py"

# ── 2. Replay 6 months of historical events ─────────────────────────────────
echo "[2/4] Replaying 6 months of synthetic historical events..."
python3 "$PROJ/scripts/replay_historical.py"

# ── 3a. Start API ────────────────────────────────────────────────────────────
echo "[3/4] Starting API on port $API_PORT ..."
lsof -ti :$API_PORT 2>/dev/null | xargs kill -9 2>/dev/null || true
sleep 1

uvicorn apps.api.main:app \
    --host 0.0.0.0 --port $API_PORT --reload \
    > /tmp/sentinel_api.log 2>&1 &
API_PID=$!

for i in $(seq 1 25); do
    if curl -sf http://localhost:$API_PORT/health | grep -q "sentinel-api" 2>/dev/null; then
        echo "      API ready — http://localhost:$API_PORT/health"
        break
    fi
    sleep 1
done

# ── 3b. Start frontend ────────────────────────────────────────────────────────
echo "[4/4] Starting Vite frontend on port $WEB_PORT ..."
lsof -ti :$WEB_PORT 2>/dev/null | xargs kill -9 2>/dev/null || true
sleep 1

cd "$PROJ/apps/web"
npm install --silent 2>/dev/null
npm run dev -- --host 0.0.0.0 --port $WEB_PORT > /tmp/sentinel_web.log 2>&1 &
WEB_PID=$!
cd "$PROJ"

sleep 4

echo ""
echo "========================================="
echo "  Ready!"
echo ""
echo "  Web app:  http://localhost:$WEB_PORT"
echo "  API docs: http://localhost:$API_PORT/docs"
echo ""
echo "  Logs:  tail -f /tmp/sentinel_api.log"
echo "         tail -f /tmp/sentinel_web.log"
echo ""
echo "  To stop: kill $API_PID $WEB_PID"
echo "========================================="

# Stream API logs (Ctrl-C to stop)
tail -f /tmp/sentinel_api.log
