.DEFAULT_GOAL := help

COMPOSE ?= docker compose

.PHONY: help up down restart build status logs logs-api logs-worker migrate test shell down-volumes

help:
	@echo "AI Workflow Rescue Docker commands:"
	@echo "  make up            Build the app image and start all services"
	@echo "  make down          Stop and remove containers (keeps database data)"
	@echo "  make restart       Restart services without rebuilding the image"
	@echo "  make build         Build the shared application image"
	@echo "  make status        Show service status"
	@echo "  make logs          Follow logs from all services"
	@echo "  make logs-api      Follow API logs"
	@echo "  make logs-worker   Follow Celery worker logs"
	@echo "  make migrate       Run database migrations"
	@echo "  make test          Run the test suite in the app image"
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

migrate:
	$(COMPOSE) run --rm migrate

test:
	$(COMPOSE) run --rm --no-deps api pytest -q

shell:
	$(COMPOSE) exec api sh

down-volumes:
	$(COMPOSE) down --volumes
