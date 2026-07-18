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
COMPOSE = docker compose --project-directory . -f infra/compose/compose.yaml
TRIVY_IMAGE = aquasec/trivy:0.69.3
UV_CACHE_DIR ?= $(CURDIR)/.cache/uv
UV_PYTHON_INSTALL_DIR ?= $(CURDIR)/.tools/python
PLAYWRIGHT_BROWSERS_PATH ?= $(CURDIR)/.cache/ms-playwright

export UV_CACHE_DIR
export UV_PYTHON_INSTALL_DIR
export PLAYWRIGHT_BROWSERS_PATH

.PHONY: setup dev personal-data-ready runtime-ready down lint typecheck test contract-test security-check smoke \
	resilience-test fixture-replay quality-gate web-e2e web-a11y source-fixture-test \
	safety-regulation-test pdf-ocr-test safety-case-test digital-case-test paper-test product-test \
	round08-test round08-eval round09-test round09-eval round10-test round10-eval \
	round11-test observability-test golden-replay load-test recovery-drill runbook-test \
	round11-evidence-test readiness-evidence slo-weekly-report \
	phase2-round13-test phase2-round14-test ai-content-preparation-test pers01-test personal-source-test personal-pilot-control-test \
	personal-content-test personal-migration-test

setup:
	$(UV) sync --frozen --all-packages
	$(PNPM) install --frozen-lockfile
	$(UV) run python -m srbg_contracts.export
	$(PNPM) contracts:generate
	$(PNPM) --filter @srbg/web exec playwright install chromium
	$(COMPOSE) build

personal-data-ready:
ifeq ($(OS),Windows_NT)
	powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/mount_personal_data.ps1
else
	test -d "$(SRBG_DATA_ROOT)"
endif

personal-pilot-control-test:
	$(COMPOSE) up --detach --wait postgres minio redis
	$(UV) run python scripts/run_isolated_integration.py \
		--migration-verifier verify_controlled_runs_migration.py -- \
		apps/api/tests/test_controlled_run_domain.py \
		apps/api/tests/test_0031_controlled_runs_migration.py \
		apps/api/tests/test_0032_controlled_run_worker_read_migration.py \
		apps/api/tests/test_0033_controlled_ai_budget_bridge_migration.py \
		tests/infrastructure/test_personal_pilot_controller.py \
		apps/worker/tests/test_controlled_ai_budget_bridge.py \
		apps/worker/tests/test_personal_source_probe_worker.py \
		apps/api/tests/test_personal_signal_event_detail.py \
		tests/infrastructure/test_production_data_isolation.py \
		apps/api/tests/test_round15_http_security.py -q

dev: personal-data-ready
	$(COMPOSE) up --build --detach --wait

runtime-ready: personal-data-ready
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
		apps/api/tests/test_pers06_evidence_gate.py \
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
		apps/api/tests/test_pers08_automatic_relationships.py \
		apps/api/tests/test_ai_gateway.py \
		apps/api/tests/test_ai_pipeline_runtime.py \
		apps/api/tests/test_ai01_content_preparation.py \
		apps/api/tests/test_ai01_orchestration.py \
		apps/api/tests/test_source_profile_replay.py \
		apps/api/tests/test_round09_feed_projection.py \
		apps/api/tests/test_pers06_publication_boundary.py \
		apps/api/tests/test_round10_discovery_domain.py \
		apps/api/tests/test_round10_portal_service.py \
		apps/api/tests/test_pers06_evidence_gate.py -q
	$(UV) run python scripts/evaluate_round09.py

ai-content-preparation-test:
	$(COMPOSE) up --detach --wait postgres minio
	$(UV) run python scripts/run_isolated_integration.py \
		--migration-verifier verify_ai01_migration.py -- \
		apps/api/tests/test_round20_migration.py \
		apps/api/tests/test_ai01_content_preparation.py \
		apps/api/tests/test_ai01_orchestration.py \
		apps/api/tests/test_ai_admin_api.py \
		apps/api/tests/test_ai_gateway.py \
		apps/api/tests/test_ai_pipeline_runtime.py \
		apps/worker/tests/test_ai_worker_isolation.py -q
	$(PNPM) --filter @srbg/web test -- ai01-content-preparation-ui.test.ts
	$(UV) run python scripts/check_ai01_no_publication_side_effects.py

pers01-test:
	$(COMPOSE) up --detach --wait postgres minio
	$(UV) run python scripts/run_isolated_integration.py \
		--migration-verifier verify_pers01_migration.py -- \
		apps/api/tests/test_pers01_migration.py \
		apps/api/tests/test_personal_source_api.py \
		packages/contracts/tests/test_personal_source_contracts.py -q
	$(PNPM) --filter @srbg/web test -- personal-sources-ui.test.ts

personal-source-test:
	$(COMPOSE) up --detach --wait postgres minio redis
	$(UV) run python scripts/run_isolated_integration.py \
		--migration-verifier verify_pers05_migration.py -- \
		apps/api/tests/test_pers05_migration.py \
		apps/api/tests/test_personal_source_discovery_domain.py \
		apps/worker/tests/test_personal_source_discovery.py \
		apps/api/tests/test_pers04_migration.py \
		apps/api/tests/test_source_profile_domain.py \
		apps/api/tests/test_source_profile_ai.py \
		apps/api/tests/test_source_profile_replay.py \
		apps/worker/tests/test_source_profile_worker.py \
		apps/api/tests/test_pers03_migration.py \
		apps/api/tests/test_personal_source_runtime.py \
		apps/api/tests/test_pers03_runtime_integration.py \
		apps/api/tests/test_pers02_migration.py \
		apps/api/tests/test_personal_source_detection.py \
		apps/api/tests/test_acquisition_security.py \
		apps/api/tests/test_round15_http_security.py \
		apps/api/tests/test_personal_source_api.py \
		packages/contracts/tests/test_pers09_contracts.py \
		packages/contracts/tests/test_personal_source_contracts.py \
		apps/worker/tests/test_personal_source_probe_worker.py -q
	$(PNPM) --filter @srbg/web test -- personal-sources-ui.test.ts pers09-personal-workspace-ui.test.ts

personal-content-test:
	$(COMPOSE) up --detach --wait postgres minio redis
	$(UV) run python scripts/run_isolated_integration.py \
		--migration-verifier verify_pers08_migration.py -- \
		apps/api/tests/test_pers08_migration.py \
		apps/api/tests/test_pers08_automatic_relationships.py \
		apps/api/tests/test_pers08_relationship_api.py \
		apps/api/tests/test_pers08_publication_boundary.py \
		apps/api/tests/test_pers09_personal_projection.py \
		packages/contracts/tests/test_pers08_relationship_contracts.py \
		apps/api/tests/test_pers07_migration.py \
		apps/api/tests/test_pers07_ai_judgments.py \
		apps/api/tests/test_pers07_signal_projection.py \
		apps/api/tests/test_pers06_migration.py \
		apps/api/tests/test_pers06_evidence_gate.py \
		apps/api/tests/test_pers06_local_evidence.py \
		apps/api/tests/test_pers06_publication_boundary.py \
		apps/api/tests/test_ai01_orchestration.py -q
	$(PNPM) --filter @srbg/web test -- ai01-content-preparation-ui.test.ts pers07-ai-signals-ui.test.ts pers08-automatic-relationships-ui.test.ts pers09-personal-workspace-ui.test.ts
	$(UV) run python scripts/evaluate_pers07.py

personal-migration-test:
	$(COMPOSE) up --detach --wait minio redis
	$(UV) run python scripts/run_pers10_migration_gate.py \
		apps/api/tests/test_pers10_migration.py \
		apps/api/tests/test_pers10_product_retirement.py \
		tests/infrastructure/test_pers10_migration_gate.py -q
	$(UV) run python scripts/evaluate_pers10.py

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
