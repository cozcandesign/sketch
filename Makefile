# MarketPulse komutları (CLAUDE.md §10). Depo kökünden çalıştırılır.
# Backend araçları backend/ içinde uv ile, süreçler kökten `uv run --project backend` ile koşar
# (böylece .env ve ./data depo kökünde kalır).

SHELL := /bin/bash
.DEFAULT_GOAL := help
NPM := npm --prefix frontend

.PHONY: help install ensure-deps dev dev-stop up down logs test test-backend test-frontend lint typecheck check migrate gen-types backfill backtest wscheck

# Çalışan kodun commit'i; süreçlere ve Docker imajına geçer, arayüzde görünür.
GIT_SHA := $(shell git rev-parse --short HEAD 2>/dev/null || echo bilinmiyor)
export MP_GIT_SHA = $(GIT_SHA)

# Geliştirme aracı doğrudan kaynaktan koşar (PYTHONPATH): paket kurulumu eskimiş olsa bile
# (ör. yeni bir pull'dan hemen sonra) `make dev-stop` çalışır.
DEV_RUNNER = PYTHONPATH=backend/src backend/.venv/bin/python -m marketpulse.devtools.runner

help: ## Komut listesi
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Bağımlılıkları kur (uv sync + npm install)
	cd backend && uv sync
	$(NPM) install

dev: ensure-deps ## api + engine + arayüz; süreçler bağımsız, çöken kendiliğinden yeniden başlar
	@test -f .env || (echo "HATA: .env yok. Once sunu calistirin: cp .env.example .env" && exit 1)
	$(DEV_RUNNER)

dev-stop: ## Arka planda kalmış geliştirme süreçlerini durdur
	@test -x backend/.venv/bin/python \
		&& $(DEV_RUNNER) --stop \
		|| echo "dev    | backend ortami yok, durdurulacak surec de yok (gerekirse: make install)"

# Ortam senkronu BURADA, bir kez yapılır. Süreçler sonra doğrudan venv python'u kullanır; böylece
# eşzamanlı `uv run` senkronu ve ondan doğabilecek "No module named marketpulse" yarışı olmaz.
ensure-deps: ## Bağımlılıkları kurar/günceller (make dev bunu kendisi çağırır)
	@test -d frontend/node_modules || (echo ">>> frontend bagimliliklari kuruluyor (ilk calistirma, birkac dakika surebilir)..." && $(NPM) install)
	@cd backend && uv sync --quiet

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

migrate: ensure-deps ## Alembic: şemayı en son sürüme getir
	backend/.venv/bin/alembic -c backend/alembic.ini upgrade head

gen-types: ensure-deps ## OpenAPI → frontend/src/api/types.gen.ts
	backend/.venv/bin/python -m marketpulse.api.openapi_export > frontend/openapi.json
	$(NPM) run gen-types

wscheck: ensure-deps ## Futures WS akışlarını dinler ve hangisinden kaç mesaj geldiğini yazar (teşhis)
	backend/.venv/bin/python -m marketpulse.devtools.wscheck $(ARGS)

backfill: ensure-deps ## Geçmiş mum verisini Binance'ten çeker (ARGS="--days 7" ile sınırlanabilir)
	backend/.venv/bin/python -m marketpulse.backfill $(ARGS)

backtest: ## Backtest motoru (Faz 7)
	@echo "backtest Faz 7'de gelir (ROADMAP F7-3)"; exit 1
