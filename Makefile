ifeq ($(OS),Windows_NT)
UV ?= $(CURDIR)/.tools/uv/uv.exe
PNPM ?= $(CURDIR)/.tools/node/pnpm.cmd
export PATH := $(CURDIR)/.tools/node;$(PATH)
else
UV ?= uv
PNPM ?= pnpm
endif

-include .env
export WEB_PORT API_PORT POSTGRES_PORT MINIO_PORT ANCHOR_MINIO_PORT
export POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB
export MINIO_ROOT_USER MINIO_ROOT_PASSWORD
export SRBG_API_DB_PASSWORD SRBG_PUBLISHER_DB_PASSWORD SRBG_PROJECTION_DB_PASSWORD
export SRBG_S3_BUCKET SRBG_S3_REGION SRBG_EXTERNAL_IO_TIMEOUT_SECONDS

POSTGRES_PORT ?= 5432
MINIO_PORT ?= 9000
ANCHOR_MINIO_PORT ?= 9002
POSTGRES_DB ?= srbg
POSTGRES_USER ?= srbg
POSTGRES_PASSWORD ?= srbg_local_only
MINIO_ROOT_USER ?= srbg_local
MINIO_ROOT_PASSWORD ?= srbg_local_storage_only
SRBG_API_DB_PASSWORD ?= srbg_api_local_only
SRBG_PUBLISHER_DB_PASSWORD ?= srbg_publisher_local_only
SRBG_PROJECTION_DB_PASSWORD ?= srbg_projection_local_only
SRBG_S3_BUCKET ?= srbg-raw
SRBG_S3_REGION ?= us-east-1
SRBG_EXTERNAL_IO_TIMEOUT_SECONDS ?= 5
ROUND17_EVIDENCE ?= $(CURDIR)/docs/acceptance/assets/round17/round17-evidence.json
ROUND17_GOLD_MANIFEST ?= $(CURDIR)/tests/gold/round17/manifest.json
ROUND17_TRUSTED_PUBLIC_KEY ?=
ROUND17_TRUSTED_PUBLIC_KEY_SHA256 ?=
ROUND17_EVAL_TRUST_ARGS = $(if $(strip $(ROUND17_TRUSTED_PUBLIC_KEY)),--trusted-public-key "$(ROUND17_TRUSTED_PUBLIC_KEY)",) $(if $(strip $(ROUND17_TRUSTED_PUBLIC_KEY_SHA256)),--trusted-public-key-sha256 "$(ROUND17_TRUSTED_PUBLIC_KEY_SHA256)",)

COMPOSE = docker compose --project-directory . -f infra/compose/compose.yaml
TRIVY_IMAGE = aquasec/trivy:0.69.3
UV_CACHE_DIR ?= $(CURDIR)/.cache/uv
UV_PYTHON_INSTALL_DIR ?= $(CURDIR)/.tools/python
PLAYWRIGHT_BROWSERS_PATH ?= $(CURDIR)/.cache/ms-playwright

export UV_CACHE_DIR
export UV_PYTHON_INSTALL_DIR
export PLAYWRIGHT_BROWSERS_PATH

.PHONY: setup dev runtime-ready down lint typecheck test contract-test security-check smoke \
	resilience-test fixture-replay quality-gate web-e2e web-a11y source-fixture-test \
	safety-regulation-test pdf-ocr-test safety-case-test digital-case-test paper-test product-test \
	round08-test round08-eval round09-test round09-eval round10-test round10-eval \
	round11-test observability-test golden-replay load-test recovery-drill runbook-test \
	round11-evidence-test readiness-evidence slo-weekly-report \
	phase2-round13-test phase2-round14-test phase2-round15-test phase2-round16-test \
	phase2-round17-test phase2-round17-eval

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
		apps/api/tests/test_round15_object_store_security.py \
		apps/api/tests/test_clamav_scanner.py \
		apps/api/tests/test_acquisition_security.py \
		apps/api/tests/test_round15_connector_contracts.py \
		apps/api/tests/test_round15_connector_replay.py \
		apps/api/tests/test_round15_http_security.py \
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
		apps/api/tests/test_round08_resolution_domain.py \
		apps/api/tests/test_round08_evaluation.py \
		apps/api/tests/test_ai_gateway.py \
		apps/api/tests/test_ai_pipeline_runtime.py \
		apps/api/tests/test_round09_feed_projection.py \
		apps/api/tests/test_round09_projection_contract.py \
		apps/api/tests/test_round10_discovery_domain.py \
		apps/api/tests/test_round10_portal_service.py \
		apps/api/tests/test_publication_service.py -q
	$(UV) run python scripts/evaluate_round09.py

quality-gate: lint typecheck test contract-test security-check

source-fixture-test:
	$(COMPOSE) up --detach --wait postgres minio
	$(UV) run python scripts/run_isolated_integration.py \
		--migration-verifier verify_round15_migration.py -- \
		apps/api/tests/test_source_fixture_integration.py -q

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

round08-test:
	$(COMPOSE) up --detach --wait postgres minio
	$(UV) run python scripts/run_isolated_integration.py -- \
		apps/api/tests/test_round08_migration.py \
		apps/api/tests/test_round08_resolution_domain.py \
		apps/api/tests/test_round08_evaluation.py \
		apps/api/tests/test_round08_integration.py \
		packages/contracts/tests/test_round08_contracts.py -q

round08-eval:
	$(UV) run python scripts/evaluate_round08.py

round09-test:
	$(COMPOSE) up --detach --wait postgres minio
	$(UV) run python scripts/run_isolated_integration.py --migration-verifier verify_round09_migration.py -- \
		apps/api/tests/test_ai_gateway.py \
		apps/api/tests/test_ai_pipeline_contracts.py \
		apps/api/tests/test_ai_pipeline_runtime.py \
		apps/api/tests/test_round09_migration.py \
		apps/api/tests/test_round09_publication_paths.py \
		apps/api/tests/test_round09_projection_contract.py \
		apps/api/tests/test_round09_feed_projection.py \
		apps/api/tests/test_publication_gate.py \
		apps/api/tests/test_publication_rbac_integration.py \
		apps/worker/tests/test_ai_worker_isolation.py \
		apps/worker/tests/test_round09_projection_worker.py -q
	$(UV) run python scripts/audit_publication_paths.py

round09-eval:
	$(UV) run python scripts/evaluate_round09.py

round10-test:
	$(COMPOSE) up --detach --wait postgres minio
	$(UV) run python scripts/run_isolated_integration.py --migration-verifier verify_round10_migration.py -- \
		apps/api/tests/test_round10_migration.py \
		apps/api/tests/test_round10_discovery_domain.py \
		apps/api/tests/test_round10_portal_api.py \
		apps/api/tests/test_round10_portal_service.py \
		apps/api/tests/test_round10_daily_publication.py \
		apps/api/tests/test_round10_security_config.py \
		apps/worker/tests/test_round10_projection_worker.py \
		packages/contracts/tests/test_round10_contracts.py -q

round10-eval: runtime-ready
	$(UV) run python scripts/evaluate_round10.py --base-url http://127.0.0.1:$(API_PORT)

web-e2e: runtime-ready
	$(PNPM) --filter @srbg/web e2e

web-a11y: runtime-ready
	$(PNPM) --filter @srbg/web a11y

round11-test:
	$(COMPOSE) up --detach --wait postgres minio
	$(UV) run python scripts/run_isolated_integration.py --migration-verifier verify_round11_migration.py -- \
		apps/api/tests/test_round11_migration.py \
		apps/api/tests/test_round11_oidc_auth.py \
		apps/api/tests/test_round11_operations_api.py \
		apps/api/tests/test_round11_operations_integration.py \
		apps/api/tests/test_round09_publication_paths.py \
		apps/api/tests/test_publication_rbac_integration.py \
		apps/worker/tests/test_round11_failure_queue.py \
		tests/infrastructure/test_round11_readiness.py \
		tests/infrastructure/test_round11_observability.py \
		tests/infrastructure/test_round11_runbooks.py -q
	$(UV) run python scripts/audit_publication_paths.py

phase2-round13-test:
	$(COMPOSE) up --detach --wait postgres minio anchor-minio
	$(COMPOSE) run --rm anchor-minio-init
	$(UV) run python scripts/run_isolated_integration.py \
		--migration-verifier verify_round13_migration.py -- \
		apps/api/tests/test_round13_access_boundary.py \
		apps/api/tests/test_round13_auth.py \
		apps/api/tests/test_round13_migration.py \
		apps/api/tests/test_round13_projection_policy.py \
		apps/api/tests/test_round13_projection_permissions.py \
		tests/infrastructure/test_round13_observability.py \
		packages/contracts/tests/test_round13_contracts.py -q
	$(UV) run python scripts/audit_publication_paths.py

phase2-round14-test:
	$(COMPOSE) up --detach --wait postgres minio
	$(UV) run python scripts/run_isolated_integration.py \
		--migration-verifier verify_round14_migration.py -- \
		apps/api/tests/test_round14_event_unification.py \
		apps/api/tests/test_round14_item_compatibility.py \
		apps/api/tests/test_round14_identity_changes.py \
		apps/api/tests/test_round14_identity_integration.py \
		apps/api/tests/test_round14_migration.py \
		apps/api/tests/test_round14_completion.py \
		tests/infrastructure/test_round14_observability.py \
		packages/contracts/tests/test_round14_contracts.py \
		apps/api/tests/test_round13_access_boundary.py \
		apps/api/tests/test_round13_projection_policy.py \
		apps/api/tests/test_publication_rbac_integration.py -q
	$(UV) run python scripts/audit_publication_paths.py

phase2-round15-test:
	$(COMPOSE) up --detach --wait postgres minio
	$(UV) run python scripts/run_isolated_integration.py \
		--migration-verifier verify_round15_migration.py -- \
		apps/api/tests/test_round15_migration.py \
		apps/api/tests/test_round15_source_lifecycle.py \
		apps/api/tests/test_round15_source_api.py \
		apps/api/tests/test_round15_source_metrics.py \
		apps/api/tests/test_logging.py \
		apps/api/tests/test_round15_scheduled_source_gate.py \
		apps/api/tests/test_round15_connector_contracts.py \
		apps/api/tests/test_round15_connector_replay.py \
		apps/api/tests/test_round15_http_security.py \
		apps/api/tests/test_acquisition_security.py \
		apps/api/tests/test_upload_security.py \
		apps/api/tests/test_pdf_security.py \
		apps/api/tests/test_document_vault_service.py \
		apps/api/tests/test_round15_object_store_security.py \
		apps/api/tests/test_source_admin_api.py \
		apps/api/tests/test_source_fixture_integration.py \
		packages/contracts/tests \
		tests/infrastructure/test_round15_observability.py \
		tests/infrastructure/test_round15_delivery.py -q
	$(PNPM) --filter @srbg/web test -- round15-source-center-ui.test.ts
	$(COMPOSE) up --build --detach --wait web
	$(PNPM) --filter @srbg/web exec playwright test \
		tests/e2e/round15-source-center.spec.ts --grep-invert @a11y
	$(PNPM) --filter @srbg/web exec playwright test \
		 tests/e2e/round15-source-center.spec.ts --grep @a11y

phase2-round16-test:
	$(COMPOSE) up --detach --wait postgres redis minio
	$(UV) run python scripts/run_isolated_integration.py \
		--migration-verifier verify_round16_migration.py -- \
		apps/api/tests/test_round16_migration.py \
		apps/api/tests/test_round16_scheduling.py \
		apps/api/tests/test_round16_scheduling_integration.py \
		apps/api/tests/test_round16_failure_records.py \
		apps/api/tests/test_round16_replay_integration.py \
		apps/api/tests/test_round16_retention.py \
		apps/api/tests/test_round16_operations_api.py \
		apps/worker/tests/test_round16_worker.py \
		tests/infrastructure/test_round16_observability.py \
		tests/infrastructure/test_round16_delivery.py -q
	$(PNPM) --filter @srbg/web test -- round16-operations-ui.test.ts

phase2-round17-test:
	$(COMPOSE) up --detach --wait postgres redis minio anchor-minio
	$(COMPOSE) run --rm anchor-minio-init
	$(UV) run python scripts/run_isolated_integration.py \
		--migration-verifier verify_round17_migration.py -- \
		apps/api/tests/test_round17_governance.py \
		apps/api/tests/test_round17_governance_migration.py \
		apps/api/tests/test_round17_pilot_domain.py \
		apps/api/tests/test_round17_pilot_api.py \
		apps/api/tests/test_round17_pilot_migration.py \
		apps/api/tests/test_round17_operations_service.py \
		apps/api/tests/test_round17_replay_origin.py \
		apps/api/tests/test_round16_replay_integration.py \
		apps/api/tests/test_round15_http_security.py \
		apps/api/tests/test_round14_event_unification.py \
		apps/api/tests/test_round14_identity_changes.py \
		apps/api/tests/test_round13_access_boundary.py \
		apps/api/tests/test_round13_projection_permissions.py \
		apps/api/tests/test_round09_publication_paths.py \
		apps/worker/tests/test_round17_worker.py \
		packages/contracts/tests/test_round17_contracts.py \
		tests/infrastructure/test_round17_eval.py \
		tests/infrastructure/test_round17_migration_verifier.py \
		tests/infrastructure/test_round17_observability.py \
		tests/infrastructure/test_round17_readiness_assets.py \
		tests/infrastructure/test_round17_delivery.py -q
	$(PNPM) --filter @srbg/web test -- round17-pilot-ui.test.ts
	$(UV) run python scripts/audit_publication_paths.py

phase2-round17-eval:
	$(UV) run python scripts/round17_eval.py \
		--evidence "$(ROUND17_EVIDENCE)" \
		--gold-manifest "$(ROUND17_GOLD_MANIFEST)" $(ROUND17_EVAL_TRUST_ARGS)

observability-test:
	$(UV) run python -m pytest tests/infrastructure/test_round11_observability.py -q

slo-weekly-report:
	$(UV) run python scripts/slo_weekly_report.py

golden-replay:
	$(UV) run python scripts/evaluate_readiness.py

load-test: runtime-ready
	$(UV) run python scripts/load_baseline.py --base-url http://127.0.0.1:$(API_PORT)

recovery-drill:
	$(UV) run python scripts/recovery_drill.py --isolated-only

runbook-test:
	$(UV) run python -m pytest tests/infrastructure/test_round11_runbooks.py -q

round11-evidence-test:
	$(UV) run python scripts/validate_round11_evidence.py

readiness-evidence:
	$(UV) run python scripts/evaluate_readiness.py \
		--readiness docs/acceptance/round-11-readiness-evidence.json
