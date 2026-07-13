# 四川路桥行业数智与安全情报平台首期 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付四川路桥内部使用的数字化与安全情报平台，打通多源采集、证据化处理、风险审核、发布、搜索和日报。

**Architecture:** Node.js 24 LTS + Nuxt 4 前端与 FastAPI 模块化单体后端组成 monorepo；API、调度、采集、解析/OCR和AI使用同一领域代码但以不同进程运行。PostgreSQL保存业务事实，Redis承载队列和缓存，S3兼容对象存储保存不可变原始证据。

**Tech Stack:** Node.js 24 LTS、Nuxt 4、Vue 3、TypeScript、Tailwind、Nuxt UI 4、Python 3.12、FastAPI、Pydantic 2、SQLAlchemy 2、Alembic、Celery 5、Redis 7、PostgreSQL 17、MinIO/S3、PyMuPDF、Playwright、OpenTelemetry、Prometheus、Grafana、Sentry。

## Global Constraints

- 首期仅企业内部，范围只含数字化情报和安全情报。
- 所有关键事实必须绑定文档版本和原文证据。
- 安全规定、事故原因、责任、伤亡和法规效力必须人工审核。
- 任何来源默认禁用，完成准入门禁后才能启用。
- 禁止绕过登录、验证码、付费墙和访问控制。
- 不引入微服务、Kafka、Kubernetes、OpenSearch、图数据库或独立向量数据库。
- 每轮采用测试驱动并形成可运行、可回滚的纵向切片。
- 所有数据库变更使用 Alembic；所有异步任务幂等。
- 时间 UTC 存储，Asia/Shanghai 展示；ID 使用 UUIDv7。证据哈希由服务端在正式采集与发布时计算，开发骨架、静态素材预览和本地演示不得因缺少哈希而阻塞。

---

## File Structure

```text
apps/web                 Nuxt用户端与管理端
apps/api                 FastAPI与领域模块
apps/worker              Celery进程入口
packages/contracts       API、枚举和Schema契约
packages/test-fixtures   合规固定来源样本
infra/compose            本地依赖
infra/migrations         Alembic
infra/monitoring         指标与看板
tests/contract           API和连接器契约
tests/e2e                用户流程
tests/quality            金标和门禁
docs/adr                 架构决策
```

### Task 1: 工程基线

**Files:**
- Create: `apps/web/**`, `apps/api/**`, `apps/worker/**`, `packages/contracts/**`
- Create: `infra/compose/compose.yaml`, `Makefile`, `.env.example`, `.github/workflows/ci.yml`
- Test: `apps/api/tests/test_health.py`, `apps/web/tests/home.spec.ts`, `tests/contract/test_version.py`

**Interfaces:**
- Produces: `/health/live`, `/health/ready`, `/api/v1/version`; Make targets used by all later tasks.

- [ ] Write failing health, version, Worker and home tests.
- [ ] Run `make test` and confirm failures identify missing services.
- [ ] Bootstrap locked dependencies, compose services, structured config and health probes.
- [ ] Implement the smallest homepage using `docs/codex-kit/assets/ui/design_tokens.json`.
- [ ] Run `make lint typecheck test contract-test security-check` and confirm zero failures.
- [ ] Commit with `feat: establish srbg insight platform foundation`.

Detailed acceptance: `docs/codex-kit/docs/codex/01-bootstrap-prompt.md`.

### Task 2: 来源注册与文档库

**Files:**
- Create: `apps/api/src/modules/source_registry/**`, `document_vault/**`
- Create: `infra/migrations/versions/*_source_vault.py`
- Create: `apps/web/pages/admin/sources/**`
- Test: `tests/contract/sources/**`, `tests/e2e/source-fixture.spec.ts`

**Interfaces:**
- Produces: `SourceService`, `RawObjectService`, `DocumentVersionService`; source and document IDs used by all processors.

- [ ] Write failing tests for source state transitions, duplicate bytes, new versions, MIME rejection and RBAC.
- [ ] Apply migration for source, policy, connector, raw object, document, version, attachment and audit.
- [ ] Implement SHA-256 object storage and manual fixture import.
- [ ] Implement source admin API and UI with default disabled seeds.
- [ ] Run `make source-fixture-test` plus global gates.
- [ ] Commit with `feat: add governed source registry and immutable document vault`.

Detailed acceptance: `docs/codex-kit/docs/codex/round-01-source-vault.md`.

### Task 3: 安全规定 HTML 纵向切片

**Files:**
- Create: `apps/api/src/modules/ingestion/**`, `parsing/**`, `intelligence/**`, `editorial/**`
- Create: `apps/web/pages/safety/**`, `apps/web/pages/admin/review/**`
- Test: `tests/fixtures/safety-regulation-html/**`, `tests/e2e/safety-regulation.spec.ts`

**Interfaces:**
- Consumes: source/document services.
- Produces: `SourceConnector`, `DocumentParser`, Claim/Evidence, review and publication contracts.

- [ ] Write failing connector, parser, evidence, review separation and E2E tests.
- [ ] Implement discover/fetch/health protocols with cursor, conditional request and SSRF controls.
- [ ] Implement HTML blocks, rules-based metadata, Claim/Evidence, the single server-authoritative `PublicationService`, and R3 review. Only the publication service database role may create publication revisions.
- [ ] Implement safety feed, detail evidence drawer and minimal review screen.
- [ ] Run fixture replay, quality gate, E2E, accessibility and global gates.
- [ ] Commit with `feat: publish evidence-backed safety regulations`.

Detailed acceptance: `docs/codex-kit/docs/codex/round-02-safety-regulation-html.md`.

### Task 4: PDF、OCR与版本变化

**Files:**
- Create: `apps/api/src/modules/parsing/pdf/**`, `parsing/ocr/**`, `document_vault/versioning/**`
- Create: `apps/web/components/evidence/PdfEvidenceViewer.vue`, `VersionDiff.vue`
- Test: `tests/fixtures/pdf/**`, `tests/quality/test_version_changes.py`

**Interfaces:**
- Produces: stable PDF/OCR locators and version invalidation events.

- [ ] Write failing tests for text PDF, scan, metadata-only change, material change, withdrawal and malicious files.
- [ ] Implement safe PDF/OCR processing and coordinate locators.
- [ ] Implement change classification and invalidation of stale claims/summaries.
- [ ] Implement evidence viewer and version timeline.
- [ ] Demonstrate v1, metadata v2, material v3 and withdrawal fixtures.
- [ ] Commit with `feat: add pdf evidence and document lifecycle versioning`.

Detailed acceptance: `docs/codex-kit/docs/codex/round-03-pdf-ocr-versioning.md`.

### Task 5: 安全事故生命周期

**Files:**
- Create: `apps/api/src/modules/events/**`, `intelligence/safety_case/**`
- Create: `apps/web/pages/safety/cases/**`, `components/events/Timeline.vue`
- Test: `tests/fixtures/safety-case-lifecycle/**`, `tests/e2e/safety-case.spec.ts`

**Interfaces:**
- Produces: Event, EventRelation and SafetyCaseProfile APIs.

- [ ] Write failing tests proving initial, follow-up, final, penalty and rectification are not deleted as duplicates.
- [ ] Implement safety fields, conflicts and official evidence constraints.
- [ ] Implement event candidate linking with hard date/region/entity rules.
- [ ] Implement fact/pending sections and lifecycle UI.
- [ ] Run lifecycle E2E and authorization gates.
- [ ] Commit with `feat: model safety incident lifecycles`.

Detailed acceptance: `docs/codex-kit/docs/codex/round-04-safety-case-lifecycle.md`.

### Task 6: 数字化案例

**Files:**
- Create: `apps/api/src/modules/intelligence/digital_case/**`, `scoring/relevance.py`
- Create: `apps/web/pages/digital/**`, `components/items/DigitalCaseCard.vue`
- Test: `tests/fixtures/digital-cases/**`, `tests/e2e/digital-case.spec.ts`

**Interfaces:**
- Produces: DigitalCaseProfile and relevance score v1.

- [ ] Write failing tests for controlled taxonomy, maturity, claimed versus verified outcomes and Sichuan relevance.
- [ ] Implement government and enterprise case adapters using fixtures.
- [ ] Implement case profile, scoring and editorial fields.
- [ ] Implement channel filters, card and detail page.
- [ ] Verify every metric links to evidence and vendor claims retain attribution.
- [ ] Commit with `feat: add evidence-aware digital transformation cases`.

Detailed acceptance: `docs/codex-kit/docs/codex/round-05-digital-cases.md`.

### Task 7: 期刊论文

**Files:**
- Create: `apps/api/src/modules/intelligence/paper/**`, `ingestion/connectors/openalex.py`, `crossref.py`
- Create: `apps/web/pages/digital/papers/**`
- Test: `tests/fixtures/openalex/**`, `crossref/**`, `tests/e2e/papers.spec.ts`

**Interfaces:**
- Produces: PaperProfile and DOI normalization.

- [ ] Write failing DOI, duplicate source, withdrawal, access-level and API contract tests.
- [ ] Implement polite API connectors with cursors, rate limits and mocks.
- [ ] Implement bibliographic profile and access policy.
- [ ] Implement paper search, detail and citation copy.
- [ ] Verify no unauthorized full text is stored or shown.
- [ ] Commit with `feat: ingest governed scholarly metadata`.

Detailed acceptance: `docs/codex-kit/docs/codex/round-06-papers.md`.

### Task 8: 软件与设备

**Files:**
- Create: `apps/api/src/modules/intelligence/product/**`
- Create: `apps/web/pages/digital/products/**`, `ProductCard.vue`
- Test: `tests/fixtures/products/**`, `tests/e2e/products.spec.ts`

**Interfaces:**
- Produces: TechnologyProductProfile, vendor/model entities and APPLIED_IN relation.

- [ ] Write failing tests for vendor claims, model versions, license unknowns and prohibited procurement conclusions.
- [ ] Implement software, IoT, low-altitude and AI product profiles.
- [ ] Implement vendor/model normalization candidates and case relations.
- [ ] Implement capability/evidence/license sections and filters.
- [ ] Verify no product page implies airspace, airworthiness or project approval.
- [ ] Commit with `feat: add governed software and equipment intelligence`.

Detailed acceptance: `docs/codex-kit/docs/codex/round-07-products-equipment.md`.

### Task 9: 去重、事件、热点和评分

**Files:**
- Create: `apps/api/src/modules/events/dedup/**`, `scoring/**`, `discovery/hot_topics/**`
- Create: `apps/web/pages/hot-topics/**`, `pages/admin/events/**`
- Test: `tests/quality/dedup/**`, `event_clusters/**`

**Interfaces:**
- Produces: candidate duplicate/cluster decisions, independent source count and score snapshots.

- [ ] Write failing gold-set tests for false merges, follow-up relations and syndicated sources.
- [ ] Implement exact and near candidate recall, hard constraints and manual decisions.
- [ ] Implement independent-source and eight-component scoring.
- [ ] Implement topic and merge/split UIs with audit.
- [ ] Run quality metrics and retain the report artifact.
- [ ] Commit with `feat: add explainable deduplication events and ranking`.

Detailed acceptance: `docs/codex-kit/docs/codex/round-08-dedup-events-scoring.md`.

### Task 10: AI与编辑发布

**Files:**
- Create: `apps/api/src/modules/ai_pipeline/**`, `editorial/gates/**`
- Create: `apps/web/pages/admin/review/**`
- Test: `tests/quality/ai/**`, `tests/security/prompt_injection/**`

**Interfaces:**
- Produces: model gateway, versioned processing runs, gate decisions and immutable publication revisions.

- [ ] Write failing Schema, forged evidence, injection, high-risk review and model-upgrade tests.
- [ ] Implement mock and configurable model providers through one gateway.
- [ ] Implement four-step prompts and strict candidate validation.
- [ ] Extend the `PublicationService` established in Task 3 with the rules in `docs/codex-kit/assets/validation/publication_gate.json`; do not create a parallel publishing path.
- [ ] Implement review, correction, withdrawal and cache/search invalidation.
- [ ] Run AI fixture replay and quality/security gates.
- [ ] Commit with `feat: add evidence-grounded ai editorial pipeline`.

Detailed acceptance: `docs/codex-kit/docs/codex/round-09-ai-editorial.md`.

### Task 11: 用户端内容产品

**Files:**
- Create: `apps/api/src/modules/discovery/**`, `reports/**`
- Create: user routes listed in `docs/codex-kit/assets/ui/page_inventory.csv`
- Test: `tests/e2e/feed-search-daily.spec.ts`, `tests/performance/search.py`

**Interfaces:**
- Produces: selected/all feed, search, daily, fingerprint, saved items and collections.

- [ ] Write failing exact-ID search, ACL, feed, daily snapshot, export and accessibility tests.
- [ ] Implement Cursor/ETag APIs and PostgreSQL search.
- [ ] Implement home, feeds, channels, search, detail, events, daily and saved pages.
- [ ] Implement fixed daily snapshot and safe Markdown export.
- [ ] Run 1080p/2K E2E, accessibility and P95 performance tests.
- [ ] Commit with `feat: deliver srbg intelligence discovery experience`.

Detailed acceptance: `docs/codex-kit/docs/codex/round-10-feed-search-daily.md`.

### Task 12: 生产门禁

**Files:**
- Create: `infra/monitoring/**`, `infra/backup/**`, `tests/quality/gold/**`, `docs/runbooks/**`
- Test: `tests/security/**`, `tests/recovery/**`, `tests/load/**`

**Interfaces:**
- Produces: SLO dashboards, alerts, recovery evidence and release readiness decision.

- [ ] Write failing alert, recovery, gold-set, security and load tests.
- [ ] Implement telemetry, dashboards, error budgets and routing.
- [ ] Implement PITR, object backup, Redis task rebuild and restore verification.
- [ ] Run security, load, cost and recovery exercises.
- [ ] Generate and validate the CI-owned readiness manifest against `docs/codex-kit/assets/validation/readiness_evidence.schema.json`; application code may report evidence but may not self-declare `PRODUCTION_READY`.
- [ ] Commit with `feat: enforce operational and production readiness gates`.

Detailed acceptance: `docs/codex-kit/docs/codex/round-11-production-gates.md`.

## Self-review result

- Spec coverage: two content domains, source governance, evidence, version, review, search, report, security and operations are mapped to tasks.
- Placeholder scan: no implementation placeholders are allowed by this plan.
- Type consistency: item types, risk levels, status and evidence roles use `docs/codex-kit/assets/taxonomy.yaml` and the step-output schemas as write contracts; `content.schema.json` is the published read model.
