.PHONY: up down build test lint migrate seed web

# ── Docker ──────────────────────────────────────────────────────────────────
up:
	docker compose up --build -d
	@echo "API:    http://localhost:8000"
	@echo "Docs:   http://localhost:8000/docs"
	@echo "Web dev: cd apps/web && npm run dev"

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f api worker beat

# ── Database ─────────────────────────────────────────────────────────────────
migrate:
	docker compose exec api alembic upgrade head

migrate-local:
	PYTHONPATH=. alembic -c apps/api/alembic.ini upgrade head

seed:
	docker compose exec api python scripts/seed_demo_regions.py

replay:
	docker compose exec api python scripts/replay_historical.py

# ── Development ──────────────────────────────────────────────────────────────
web:
	cd apps/web && npm install && npm run dev

api-dev:
	PYTHONPATH=. uvicorn apps.api.main:app --reload --port 8000

worker-dev:
	PYTHONPATH=. celery -A apps.worker.celery_app worker --loglevel=debug --concurrency=2

beat-dev:
	PYTHONPATH=. celery -A apps.worker.celery_app beat --loglevel=debug

# ── Tests ────────────────────────────────────────────────────────────────────
test:
	PYTHONPATH=. pytest apps/api/tests/ -v --tb=short

test-watch:
	PYTHONPATH=. pytest apps/api/tests/ -v --tb=short -f

lint:
	ruff check apps/ ml/ scripts/
	cd apps/web && npm run type-check

# ── ML ───────────────────────────────────────────────────────────────────────
train-construction:
	PYTHONPATH=. python ml/train_construction.py

train-solar:
	PYTHONPATH=. python ml/train_solar.py

eval-models:
	PYTHONPATH=. python ml/eval.py

# ── Admin ────────────────────────────────────────────────────────────────────
scan-region:
	@read -p "Region ID: " rid; \
	curl -s -X POST http://localhost:8000/api/admin/scan/$$rid | python3 -m json.tool

scan-all:
	curl -s -X POST http://localhost:8000/api/admin/scan-all | python3 -m json.tool

stats:
	curl -s http://localhost:8000/api/stats | python3 -m json.tool
