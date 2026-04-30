.PHONY: help bootstrap install lint format typecheck test dev-api dev-worker dev-up dev-down migrate migrate-rev migrate-down clean

PNPM         ?= pnpm
UV           ?= uv
API_PORT     ?= 7878
WORKER_HEALTH_PORT ?= 7879

help:
	@echo "Liftwork — common dev targets"
	@echo "  make bootstrap   Install Python + Node deps and pre-commit"
	@echo "  make install     uv sync + pnpm install"
	@echo "  make lint        ruff check + format check"
	@echo "  make format      ruff format + ruff check --fix"
	@echo "  make typecheck   mypy across all members"
	@echo "  make test        pytest across all members"
	@echo "  make dev-up      docker-compose up -d (postgres + redis)"
	@echo "  make dev-down    docker-compose down"
	@echo "  make dev-api     run the FastAPI app with reload"
	@echo "  make dev-worker  run the arq worker"
	@echo "  make migrate          alembic upgrade head"
	@echo "  make migrate-rev m=msg  alembic revision --autogenerate -m \"\$$m\""
	@echo "  make migrate-down       alembic downgrade -1"

bootstrap: install
	$(UV) run pre-commit install

install:
	$(UV) sync --all-packages
	cd apps/dashboard 2>/dev/null && $(PNPM) install || true

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .

format:
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

typecheck:
	$(UV) run mypy apps/api/src apps/worker/src packages/core/src

test:
	$(UV) run pytest

dev-up:
	docker compose -f deploy/docker-compose.yaml up -d

dev-down:
	docker compose -f deploy/docker-compose.yaml down

dev-api:
	$(UV) run --package liftwork-api uvicorn liftwork_api.main:app --reload --host 0.0.0.0 --port $(API_PORT)

dev-worker:
	$(UV) run --package liftwork-worker python -m liftwork_worker.main

migrate:
	$(UV) run alembic upgrade head

migrate-rev:
	@test -n "$(m)" || (echo "usage: make migrate-rev m='describe change'" && exit 1)
	$(UV) run alembic revision --autogenerate -m "$(m)"

migrate-down:
	$(UV) run alembic downgrade -1

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
	find . -type d -name .ruff_cache -prune -exec rm -rf {} +
	find . -type d -name .mypy_cache -prune -exec rm -rf {} +
