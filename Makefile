.PHONY: up down build logs ps shell-user shell-order migrate seed test lint

up:
	cp -n .env.example .env || true
	docker compose up -d
	@echo "Services starting... run 'make logs' to watch"

down:
	docker compose down -v

build:
	docker compose build --no-cache

logs:
	docker compose logs -f

ps:
	docker compose ps

migrate:
	docker compose exec user-service alembic upgrade head
	docker compose exec product-service alembic upgrade head
	docker compose exec order-service alembic upgrade head

seed:
	docker compose exec user-service python -m scripts.seed_db

test:
	docker compose exec user-service pytest tests/ -v --cov=app
	docker compose exec product-service pytest tests/ -v --cov=app
	docker compose exec order-service pytest tests/ -v --cov=app

lint:
	docker compose exec user-service ruff check app/
	docker compose exec product-service ruff check app/
	docker compose exec order-service ruff check app/

shell-user:
	docker compose exec user-service bash

shell-order:
	docker compose exec order-service bash

cloud-up:
	cd infra/terraform && terraform init && terraform apply -auto-approve

cloud-down:
	cd infra/terraform && terraform destroy -auto-approve

test:
	docker compose exec user-service python -m pytest tests/ -v --cov=app --cov-report=term-missing
	docker compose exec product-service python -m pytest tests/ -v --cov=app --cov-report=term-missing
	docker compose exec order-service python -m pytest tests/ -v --cov=app --cov-report=term-missing
