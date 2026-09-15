# MarketPulse komutları (CLAUDE.md §10). Depo kökünden çalıştırılır.
# Backend araçları backend/ içinde uv ile, süreçler kökten `uv run --project backend` ile koşar
# (böylece .env ve ./data depo kökünde kalır).

SHELL := /bin/bash
.DEFAULT_GOAL := help
NPM := npm --prefix frontend

.PHONY: help install dev up down logs test test-backend test-frontend lint typecheck check migrate gen-types backfill backtest

help: ## Komut listesi
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Bağımlılıkları kur (uv sync + npm install)
	cd backend && uv sync
	$(NPM) install

dev: ## api (reload) + engine + Vite dev server'ı birlikte başlat
	@test -f .env || (echo "HATA: .env yok. Önce: cp .env.example .env" && exit 1)
	uv run --project backend honcho start -f Procfile.dev

up: ## Docker: üç servisi kur ve başlat
	docker compose up -d --build

down: ## Docker: servisleri durdur
	docker compose down

logs: ## Docker: logları izle
	docker compose logs -f --tail=200

test-backend: ## Backend testleri (pytest)
	cd backend && uv run pytest

test-frontend: ## Frontend testleri (vitest)
	$(NPM) run test

test: test-backend test-frontend ## Tüm testler

lint: ## ruff + import-linter + eslint + prettier
	cd backend && uv run ruff check src tests alembic
	cd backend && uv run ruff format --check src tests alembic
	cd backend && uv run lint-imports
	$(NPM) run lint
	$(NPM) run format:check

typecheck: ## mypy --strict + tsc
	cd backend && uv run mypy
	$(NPM) run typecheck

check: lint typecheck test ## Commit öncesi zorunlu: lint + typecheck + test

migrate: ## Alembic: şemayı en son sürüme getir
	uv run --project backend alembic -c backend/alembic.ini upgrade head

gen-types: ## OpenAPI → frontend/src/api/types.gen.ts
	uv run --project backend python -m marketpulse.api.openapi_export > frontend/openapi.json
	$(NPM) run gen-types

backfill: ## Geçmiş veri çek (Faz 1, F1-13)
	@echo "backfill Faz 1'de gelir (ROADMAP F1-13)"; exit 1

backtest: ## Backtest motoru (Faz 7)
	@echo "backtest Faz 7'de gelir (ROADMAP F7-3)"; exit 1
