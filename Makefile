ifeq ($(OS),Windows_NT)
UV ?= $(CURDIR)/.tools/uv/uv.exe
PNPM ?= $(CURDIR)/.tools/node/pnpm.cmd
export PATH := $(CURDIR)/.tools/node;$(PATH)
else
UV ?= uv
PNPM ?= pnpm
endif

-include .env
export WEB_PORT API_PORT POSTGRES_PORT MINIO_PORT
export POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB
export MINIO_ROOT_USER MINIO_ROOT_PASSWORD
export SRBG_API_DB_PASSWORD SRBG_PUBLISHER_DB_PASSWORD
export SRBG_S3_BUCKET SRBG_S3_REGION SRBG_EXTERNAL_IO_TIMEOUT_SECONDS

POSTGRES_PORT ?= 5432
MINIO_PORT ?= 9000
POSTGRES_DB ?= srbg
POSTGRES_USER ?= srbg
POSTGRES_PASSWORD ?= srbg_local_only
MINIO_ROOT_USER ?= srbg_local
MINIO_ROOT_PASSWORD ?= srbg_local_storage_only
SRBG_API_DB_PASSWORD ?= srbg_api_local_only
SRBG_PUBLISHER_DB_PASSWORD ?= srbg_publisher_local_only
SRBG_S3_BUCKET ?= srbg-raw
SRBG_S3_REGION ?= us-east-1
SRBG_EXTERNAL_IO_TIMEOUT_SECONDS ?= 5

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
	resilience-test fixture-replay quality-gate web-e2e web-a11y source-fixture-test \
	safety-regulation-test pdf-ocr-test safety-case-test digital-case-test paper-test product-test

setup:
	$(UV) sync --frozen --all-packages
	$(PNPM) install --frozen-lockfile
	$(UV) run python -m srbg_contracts.export
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
	$(UV) run python scripts/check_contract_generation.py
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
		apps/api/tests/test_clamav_scanner.py \
		apps/api/tests/test_acquisition_security.py \
		apps/api/tests/test_safety_regulation_parser.py \
		apps/api/tests/test_safety_regulation_pipeline.py \
		apps/api/tests/test_publication_gate.py \
		apps/api/tests/test_publication_gate_v4.py \
		apps/api/tests/test_publication_gate_v5.py \
		apps/api/tests/test_publication_gate_v6.py \
		apps/api/tests/test_publication_gate_v7.py \
		apps/api/tests/test_safety_case_domain.py \
		apps/api/tests/test_safety_case_candidate_service.py \
		apps/api/tests/test_round04_official_fixtures.py \
		apps/api/tests/test_digital_case_domain.py \
		apps/api/tests/test_digital_case_source.py \
		apps/api/tests/test_round05_fixtures.py \
		apps/api/tests/test_round06_fixtures.py \
		apps/api/tests/test_paper_domain.py \
		apps/api/tests/test_paper_source.py \
		apps/api/tests/test_round07_fixtures.py \
		apps/api/tests/test_technology_product_domain.py \
		apps/api/tests/test_technology_product_source.py \
		apps/api/tests/test_publication_service.py -q

quality-gate: lint typecheck test contract-test security-check

source-fixture-test:
	$(COMPOSE) up --detach --wait postgres minio
	$(COMPOSE) run --rm minio-init
	$(SOURCE_DB_ENV) $(UV) run alembic -c apps/api/alembic.ini upgrade head
	$(SOURCE_TEST_ENV) $(UV) run python -m pytest apps/api/tests/test_source_fixture_integration.py -q

safety-regulation-test:
	$(COMPOSE) up --detach --wait postgres minio
	$(UV) run python scripts/run_isolated_integration.py -- \
		apps/api/tests/test_safety_regulation_integration.py \
		apps/api/tests/test_publication_rbac_integration.py -q

pdf-ocr-test:
	$(COMPOSE) up --detach --wait postgres redis clamav minio
	$(COMPOSE) run --rm --no-deps parser python scripts/verify_round03_ocr.py
	$(UV) run python scripts/run_isolated_integration.py -- \
		apps/api/tests/test_round03_golden_fixtures.py \
		apps/api/tests/test_pdf_security.py \
		apps/api/tests/test_pdf_parser.py \
		apps/api/tests/test_pdf_versioning.py \
		apps/api/tests/test_safety_regulation_integration.py -q

safety-case-test:
	$(COMPOSE) up --detach --wait postgres minio
	$(UV) run python scripts/run_isolated_integration.py -- \
		apps/api/tests/test_safety_case_integration.py \
		apps/api/tests/test_round04_official_fixtures.py -q

digital-case-test:
	$(COMPOSE) up --detach --wait postgres minio
	$(UV) run python scripts/run_isolated_integration.py -- \
		apps/api/tests/test_round05_migration.py \
		apps/api/tests/test_round05_fixtures.py \
		apps/api/tests/test_digital_case_domain.py \
		apps/api/tests/test_digital_case_source.py \
		apps/api/tests/test_publication_gate_v5.py -q

paper-test:
	$(COMPOSE) up --detach --wait postgres minio
	$(UV) run python scripts/run_isolated_integration.py -- \
		apps/api/tests/test_round06_migration.py \
		apps/api/tests/test_round06_fixtures.py \
		apps/api/tests/test_paper_domain.py \
		apps/api/tests/test_paper_source.py \
		apps/api/tests/test_publication_gate_v6.py \
		packages/contracts/tests/test_paper_contracts.py -q

product-test:
	$(COMPOSE) up --detach --wait postgres minio
	$(UV) run python scripts/run_isolated_integration.py -- \
		apps/api/tests/test_round07_migration.py \
		apps/api/tests/test_round07_fixtures.py \
		apps/api/tests/test_technology_product_domain.py \
		apps/api/tests/test_technology_product_source.py \
		apps/api/tests/test_technology_product_query.py \
		apps/api/tests/test_technology_product_metrics.py \
		apps/api/tests/test_publication_gate_v7.py \
		apps/api/tests/test_publication_repository_round07.py \
		packages/contracts/tests/test_technology_product_contracts.py -q

web-e2e: runtime-ready
	$(PNPM) --filter @srbg/web e2e

web-a11y: runtime-ready
	$(PNPM) --filter @srbg/web a11y
