ifeq ($(OS),Windows_NT)
UV ?= $(CURDIR)/.tools/uv/uv.exe
PNPM ?= $(CURDIR)/.tools/node/pnpm.cmd
export PATH := $(CURDIR)/.tools/node;$(PATH)
else
UV ?= uv
PNPM ?= pnpm
endif

-include .env
export WEB_PORT API_PORT

POSTGRES_PORT ?= 5432
MINIO_PORT ?= 9000

COMPOSE = docker compose --project-directory . -f infra/compose/compose.yaml
TRIVY_IMAGE = aquasec/trivy:0.69.3
ifeq ($(OS),Windows_NT)
SOURCE_DB_ENV = set "SRBG_DATABASE_URL=postgresql+asyncpg://srbg:srbg_local_only@127.0.0.1:$(POSTGRES_PORT)/srbg" &&
SOURCE_TEST_ENV = set "SRBG_RUN_SOURCE_INTEGRATION=1" && set "SRBG_DATABASE_URL=postgresql+asyncpg://srbg:srbg_local_only@127.0.0.1:$(POSTGRES_PORT)/srbg" && set "SRBG_S3_ENDPOINT_URL=http://127.0.0.1:$(MINIO_PORT)" &&
else
SOURCE_DB_ENV = SRBG_DATABASE_URL=postgresql+asyncpg://srbg:srbg_local_only@127.0.0.1:$(POSTGRES_PORT)/srbg
SOURCE_TEST_ENV = SRBG_RUN_SOURCE_INTEGRATION=1 SRBG_DATABASE_URL=postgresql+asyncpg://srbg:srbg_local_only@127.0.0.1:$(POSTGRES_PORT)/srbg SRBG_S3_ENDPOINT_URL=http://127.0.0.1:$(MINIO_PORT)
endif
UV_CACHE_DIR ?= $(CURDIR)/.cache/uv
UV_PYTHON_INSTALL_DIR ?= $(CURDIR)/.tools/python
PLAYWRIGHT_BROWSERS_PATH ?= $(CURDIR)/.cache/ms-playwright

export UV_CACHE_DIR
export UV_PYTHON_INSTALL_DIR
export PLAYWRIGHT_BROWSERS_PATH

.PHONY: setup dev runtime-ready down lint typecheck test contract-test security-check smoke \
	resilience-test fixture-replay quality-gate web-e2e web-a11y source-fixture-test

setup:
	$(UV) sync --frozen --all-packages
	$(PNPM) install --frozen-lockfile
	$(PNPM) contracts:generate
	$(PNPM) --filter @srbg/web exec playwright install chromium
	$(COMPOSE) build

dev:
	$(COMPOSE) up --build --detach --wait

runtime-ready:
	$(COMPOSE) up --detach --wait

down:
	$(COMPOSE) down --remove-orphans

lint:
	$(UV) run ruff check .
	$(PNPM) tokens:check
	$(PNPM) --filter @srbg/ui lint
	$(PNPM) --filter @srbg/web lint

typecheck:
	$(UV) run mypy
	$(PNPM) --filter @srbg/ui typecheck
	$(PNPM) --filter @srbg/web typecheck
	$(PNPM) --filter @srbg/web exec tsc --noEmit --skipLibCheck false ../../packages/contracts/generated/types/index.d.ts

test:
	$(UV) run python -m pytest
	$(PNPM) --filter @srbg/ui test
	$(PNPM) --filter @srbg/web test

contract-test:
	$(PNPM) contracts:generate
	git diff --exit-code -- packages/contracts/generated
	$(UV) run python -m pytest packages/contracts/tests tests/contract -q

security-check:
	$(UV) run pip-audit
	$(PNPM) audit --prod --audit-level high
	$(UV) run python scripts/prepare_security_scan.py
	docker run --rm -v "$(CURDIR)/.cache/trivy-input:/workspace:ro" -w /workspace \
		$(TRIVY_IMAGE) fs --scanners secret,misconfig --exit-code 1 \
		--severity HIGH,CRITICAL --skip-version-check .

smoke:
	$(UV) run python scripts/smoke.py

resilience-test:
	$(UV) run python -m scripts.resilience_test

fixture-replay:
	$(UV) run python -m pytest \
		apps/api/tests/test_upload_security.py \
		apps/api/tests/test_document_vault_service.py \
		apps/api/tests/test_clamav_scanner.py -q

quality-gate: lint typecheck test contract-test security-check

source-fixture-test:
	$(COMPOSE) up --detach --wait postgres minio
	$(COMPOSE) run --rm minio-init
	$(SOURCE_DB_ENV) $(UV) run alembic -c apps/api/alembic.ini upgrade head
	$(SOURCE_TEST_ENV) $(UV) run python -m pytest apps/api/tests/test_source_fixture_integration.py -q

web-e2e: runtime-ready
	$(PNPM) --filter @srbg/web e2e

web-a11y: runtime-ready
	$(PNPM) --filter @srbg/web a11y
