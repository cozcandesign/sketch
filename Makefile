# MarketPulse komutları (CLAUDE.md §10). Depo kökünden çalıştırılır.
# Backend araçları backend/ içinde uv ile, süreçler kökten `uv run --project backend` ile koşar
# (böylece .env ve ./data depo kökünde kalır).

SHELL := /bin/bash
.DEFAULT_GOAL := help
NPM := npm --prefix frontend

.PHONY: help install ensure-deps dev up down logs test test-backend test-frontend lint typecheck check migrate gen-types backfill backtest

help: ## Komut listesi
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Bağımlılıkları kur (uv sync + npm install)
	cd backend && uv sync
	$(NPM) install

dev: ensure-deps ## api (reload) + engine + Vite dev server'ı birlikte başlat
	@test -f .env || (echo "HATA: .env yok. Once sunu calistirin: cp .env.example .env" && exit 1)
	uv run --project backend honcho start -f Procfile.dev

ensure-deps: ## Eksik bağımlılıkları sessizce kurar (make dev bunu kendisi çağırır)
	@test -d frontend/node_modules || (echo ">>> frontend bagimliliklari kuruluyor (ilk calistirma, birkac dakika surebilir)..." && $(NPM) install)
	@test -x backend/.venv/bin/python || (echo ">>> backend bagimliliklari kuruluyor..." && cd backend && uv sync)

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

backfill: ## Geçmiş mum verisini Binance'ten çeker (ARGS="--days 7" ile sınırlanabilir)
	uv run --project backend python -m marketpulse.backfill $(ARGS)

backtest: ## Backtest motoru (Faz 7)
	@echo "backtest Faz 7'de gelir (ROADMAP F7-3)"; exit 1
