.PHONY: help dev backend-only prod build clean format lint typecheck test shell-db migration

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

dev: ## Start development environment with hot reload
	docker compose -f docker-compose.yml -f docker-compose.override.yml up --build

dev-d: ## Start development environment with hot reload in detached mode
	docker compose -f docker-compose.yml -f docker-compose.override.yml up --build -d

backend-only: ## Start only backend services (for frontend development)
	docker compose -f docker-compose.yml -f docker-compose.override.yml up --build api worker beat redis db

prod: ## Start production environment
	docker compose up --build

build: ## Build all images
	docker compose build

clean: ## Clean up containers and volumes
	docker compose down -v --remove-orphans
	docker system prune -f

format: ## Format code with black
	black --line-length 120 backend/app/ tests/

format-check: ## Check code formatting
	black --check --line-length 120 backend/app tests

lint: ## Lint code with ruff
	ruff check backend/app/ tests/ --fix

typecheck: ## Type check with mypy
	mypy backend/app/

test: ## Run tests
	SKIP_STARTUP_VALIDATION=1 pytest

check: ## Run all quality checks
	$(MAKE) lint format-check typecheck test

shell-db: ## Open database shell
	docker compose exec db psql -U mastowatch -d mastowatch

migration: ## Create new migration (usage: make migration name="description")
	docker compose run --rm migrate alembic revision --autogenerate -m "$(name)"

logs-api: ## Show API logs
	docker compose logs -f api

logs-worker: ## Show worker logs
	docker compose logs -f worker

logs-frontend: ## Show frontend logs
	docker compose logs -f frontend

logs: ## Show logs for all services
	docker compose logs -f

stop: ## Stop all services
	docker compose down

restart-api: ## Restart API service
	docker compose restart api

restart-worker: ## Restart worker service
	docker compose restart worker

restart-frontend: ## Restart frontend service
	docker compose restart frontend

status: ## Show service status
	docker compose ps

shell-api: ## Enter API container shell
	docker compose exec api bash

docker-build: ## Build with BuildKit
	DOCKER_BUILDKIT=1 docker compose build

docker-up: ## Start with BuildKit
	DOCKER_BUILDKIT=1 docker compose up
