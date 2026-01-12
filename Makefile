# Makefile for Product Service

.PHONY: help install dev run-api run-worker run-parser test lint format migrate docker-up docker-down clean

# Default target
help:
	@echo "Product Service - Available Commands"
	@echo ""
	@echo "Development:"
	@echo "  make install     - Install dependencies"
	@echo "  make dev         - Install dev dependencies"
	@echo "  make run-api     - Run API server locally"
	@echo "  make run-worker  - Run enrichment worker locally"
	@echo "  make run-parser  - Run parser service locally"
	@echo ""
	@echo "Database:"
	@echo "  make migrate     - Run database migrations"
	@echo "  make migrate-status - Show migration status"
	@echo ""
	@echo "Testing:"
	@echo "  make test        - Run all tests"
	@echo "  make test-unit   - Run unit tests"
	@echo "  make test-int    - Run integration tests"
	@echo "  make coverage    - Run tests with coverage report"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint        - Run linters"
	@echo "  make format      - Format code"
	@echo "  make typecheck   - Run type checker"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-up   - Start all services with docker-compose"
	@echo "  make docker-down - Stop all services"
	@echo "  make docker-build - Build Docker images"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean       - Remove build artifacts"

# Installation
install:
	pip install -r requirements.txt
	playwright install chromium

dev:
	pip install -r requirements.txt
	pip install -e .
	playwright install chromium

# Running
run-api:
	cd cmd/api && python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

run-worker:
	cd cmd/worker-enrichment && python main.py

run-sync-worker:
	cd cmd/worker-sync && python main.py

run-parser:
	cd parser_service/cmd && python main.py

# Database
migrate:
	cd cmd/migrator && python main.py

migrate-status:
	@echo "Checking migration status..."
	cd cmd/migrator && python -c "import asyncio; from main import get_applied_migrations; print(asyncio.run(get_applied_migrations()))"

# Testing
test:
	pytest tests/ -v

test-unit:
	pytest tests/unit/ -v

test-int:
	pytest tests/integration/ -v

test-e2e:
	pytest tests/e2e/ -v

coverage:
	pytest tests/ --cov=internal --cov=pkg --cov-report=html --cov-report=term-missing

# Code Quality
lint:
	flake8 internal pkg cmd tests
	mypy internal pkg cmd

format:
	black internal pkg cmd tests
	isort internal pkg cmd tests

typecheck:
	mypy internal pkg cmd --ignore-missing-imports

# Docker
docker-up:
	docker-compose -f deploy/docker/docker-compose.yml up -d

docker-down:
	docker-compose -f deploy/docker/docker-compose.yml down

docker-build:
	docker build -f deploy/docker/Dockerfile.api -t product-service-api:latest .
	docker build -f deploy/docker/Dockerfile.worker -t product-service-worker:latest .

docker-logs:
	docker-compose -f deploy/docker/docker-compose.yml logs -f

# Cleanup
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf build/ dist/ .coverage htmlcov/

# Health Check
health:
	curl -s http://localhost:8000/api/v1/products/health | jq .
