.DEFAULT_GOAL := help

COMPOSE ?= docker compose

.PHONY: help up down restart build status logs logs-api logs-worker logs-outbox migrate test shell down-volumes seed scenarios demo eval eval-offline lint

help:
	@echo "AI Workflow Rescue Docker commands:"
	@echo "  make up            Build the images and start everything (UI on http://127.0.0.1:3000)"
	@echo "  make down          Stop and remove containers (keeps database data)"
	@echo "  make restart       Restart services without rebuilding the image"
	@echo "  make build         Build the shared application image"
	@echo "  make status        Show service status"
	@echo "  make logs          Follow logs from all services"
	@echo "  make logs-api      Follow API logs"
	@echo "  make logs-worker   Follow Celery worker logs"
	@echo "  make logs-frontend Follow frontend (nginx) logs"
	@echo "  make logs-outbox   Follow outbox dispatcher logs"
	@echo "  make migrate       Run database migrations"
	@echo "  make test          Run the test suite (mounts ./tests into the app image)"
	@echo "  make seed          Create the admin (ADMIN_PASSWORD) and a dev operator"
	@echo "  make scenarios     Run every failure scenario through the API"
	@echo "  make demo          Uncertain-outcome recovery demo (DEMO_ARGS=--investigate for AI)"
	@echo "  make eval          Evaluate the AI investigator with the real model (EVAL_ARGS=--repeat 3)"
	@echo "  make eval-offline  Stress-test the guardrails with bad answers (no API key)"
	@echo "  make lint          Run ruff"
	@echo "  make shell         Open a shell in the running API container"
	@echo "  make down-volumes  Remove containers and database data"

up:
	$(COMPOSE) up --build -d

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart

build:
	$(COMPOSE) build migrate

status:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f

logs-api:
	$(COMPOSE) logs -f api

logs-worker:
	$(COMPOSE) logs -f worker

logs-frontend:
	$(COMPOSE) logs -f frontend

logs-outbox:
	$(COMPOSE) logs -f outbox

seed:
	$(COMPOSE) run --rm --no-deps -e ADMIN_USERNAME -e ADMIN_EMAIL -e ADMIN_PASSWORD api python scripts/seed_data.py

scenarios:
	python3 backend/scripts/simulate_failure.py scenarios

demo:
	python3 backend/scripts/simulate_failure.py demo $(DEMO_ARGS)

eval:
	$(COMPOSE) run --rm --no-deps api python scripts/evaluate_investigator.py $(EVAL_ARGS)

eval-offline:
	$(COMPOSE) run --rm --no-deps api python scripts/evaluate_investigator.py --offline

lint:
	docker run --rm -v "$$PWD/backend":/w -w /w python:3.12-slim sh -c "pip install -q ruff && ruff check . --no-cache"

migrate:
	$(COMPOSE) run --rm migrate

test:
	$(COMPOSE) --profile test run --rm test

shell:
	$(COMPOSE) exec api sh

down-volumes:
	$(COMPOSE) down --volumes --remove-orphans
