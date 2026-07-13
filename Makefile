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

COMPOSE = docker compose --project-directory . -f infra/compose/compose.yaml
TRIVY_IMAGE = aquasec/trivy:0.69.3
UV_CACHE_DIR ?= $(CURDIR)/.cache/uv
UV_PYTHON_INSTALL_DIR ?= $(CURDIR)/.tools/python
PLAYWRIGHT_BROWSERS_PATH ?= $(CURDIR)/.cache/ms-playwright

export UV_CACHE_DIR
export UV_PYTHON_INSTALL_DIR
export PLAYWRIGHT_BROWSERS_PATH

.PHONY: setup dev runtime-ready down lint typecheck test contract-test security-check smoke \
	resilience-test fixture-replay quality-gate web-e2e web-a11y

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
	$(PNPM) --filter @srbg/web lint

typecheck:
	$(UV) run mypy
	$(PNPM) --filter @srbg/web typecheck
	$(PNPM) --filter @srbg/web exec tsc --noEmit --skipLibCheck false ../../packages/contracts/generated/types/index.d.ts

test:
	$(UV) run python -m pytest
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
	@echo "Round 00 has no content adapters or replay fixtures."

quality-gate: lint typecheck test contract-test security-check

web-e2e: runtime-ready
	$(PNPM) --filter @srbg/web e2e

web-a11y: runtime-ready
	$(PNPM) --filter @srbg/web a11y
