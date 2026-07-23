# T45 Safety holds and Owner decisions acceptance

Issue #45 implements the Safety lifecycle under parent Spec #40. It extends the
single #43 Owner exception control plane and reuses the #44 suppression service;
it does not add a parallel review queue, a second Owner console, or a publication
status shortcut.

## Preconditions and isolation

- Fetched `origin --prune` before worktree creation.
- Based `codex/issue-45-safety-holds` on remote integration commit
  `6d6d373a4acd7f8d6c4fb2023d1ba5ecbf3389d5`.
- Verified the #43 and #44 feature and merge commits are ancestors of the remote
  integration branch.
- Created the clean independent worktree
  `D:\CodexProjects\srbg-intelligence-platform-issue-45`.
- Confirmed one Alembic head and dynamically extended
  `0052_feed_suppression_projection` with
  `0053_safety_exception_lifecycle`.
- Used the isolated Compose project `srbg-issue45` with PostgreSQL `55445`,
  Redis `56445`, MinIO `59447`, MinIO console `59448`, anchor MinIO `59449`,
  API `58445`, and Web `30445`.

## Delivered behavior

- Pre-scan findings and validated AI `security_signals` enter one
  `SAFETY_HOLD` decision path. The server maps prompt-injection and suspicious
  model signals to `OWNER_DECIDABLE`; private-network, loopback, cloud-metadata,
  malicious-payload, access-control-bypass, mandatory-malware-scan, missing-safe-
  bytes, and every unknown signal fail closed as `HARD_BLOCK`.
- Pre-scan holds continue through the ordinary classifier so an allow action has
  evidence-backed publication context. AI-signal candidates independently run
  every ordinary relevance, primary-type, domain-axis, and evidence-locator
  rule; only a candidate whose sole remaining failure is the Safety signal may
  be materialized. An invalid candidate remains held without gaining a
  qualification acceptance or publication path.
- The restricted `record_safety_exception_v2` database command creates the
  shared `owner_exception_v2` record, its append-only `CREATED` event, and a
  tamper-evident audit record. Worker roles do not receive direct write access to
  the exception or audit tables.
- The existing `/api/v2/owner/exceptions` list, detail, and command routes now
  serve Technical and Safety exceptions. Safety projections expose only bounded
  reason codes, generic safe titles, safe evidence identifiers, state, and
  timestamps; they do not expose raw document bytes, media, extracted text,
  prompt fragments, or model output.
- Safety commands require local Owner identity, UUID idempotency keys, and
  optimistic `If-Match`. An advisory lock covers the complete publication
  effect, and a durable `PENDING` action is resumed after interruption, making
  concurrent or restarted same-key requests converge on one truthful result.
- `ALLOW_FEED` is available only for `OWNER_DECIDABLE`. It appends the Owner
  decision and invokes `PublicationService.refresh_v2_projection` against the
  current authoritative context. A passing result automatically restores the
  Feed projection and resolves the exception; a failing gate remains open and
  returns a deterministic Problem Details response. No second confirmation or
  direct publication-state write exists.
- `DENY_FEED` calls the existing #44 suppression command with EVENT scope and
  `SAFETY_DENIAL`, then resolves the exception. It does not duplicate
  suppression storage or matching logic.
- `HARD_BLOCK` never renders an allow action and the API rejects attempted
  allowance with `SAFETY_HARD_BLOCK_NON_OVERRIDABLE`. Unknown future signals are
  hard blocks rather than implicit Owner decisions.
- Migration 0053 adds the narrow Safety decision uniqueness rule and excludes
  every open Safety exception from the existing server-side visible projection.
  Feed, search, hotspot, Event detail, Reader appendix, and media therefore
  remain filtered in SQL before data reaches the browser.
- The existing Owner page is generalized as one Technical/Safety workspace,
  preserving escaped output, keyboard controls, responsive reflow, and explicit
  hard-block presentation.
- Metrics report only bounded Safety backlog and command action/outcome labels.

## TDD and verification evidence

- The existing highest autonomous SourceStream seam covers normal publication
  followed by a Safety hold, SQL-boundary exclusion from Feed/search/hotspot/
  Event/appendix/media, concurrent same-key Owner commands, automatic gated
  restoration for an allowed `SAFETY_INTELLIGENCE` Event, exactly one
  `SAFETY_DENIAL` suppression for a denied `INDUSTRY_UPDATE` Event, and a live
  malicious-payload `HARD_BLOCK` that cannot create an allow event or projection.
- Real isolated PostgreSQL migration replay passed upgrade to 0053, downgrade to
  0052, and re-upgrade to 0053. The autonomous migration verifier also preserves
  its earlier linear replay.
- Focused contract, policy, API, Worker, migration, and integration suites
  passed. The isolated highest seam's accepted ALLOW/DENY cases passed 2/2 and
  migration plus hard-block case passed 1/1.
- `make lint`: passed.
- `make typecheck`: passed (mypy strict across 155 source files plus generated
  contracts and Vue/Nuxt TypeScript).
- `make test`: passed (Python 1532 passed / 27 skipped, UI 53 passed, Web 106
  passed).
- `make contract-test`: passed (reproducible generation and 123 contract tests).
- `make security-check`: passed (Python and production JavaScript dependency
  audits plus Trivy HIGH/CRITICAL secret and configuration scan).
- `make fixture-replay`: passed (376 tests and the offline evaluation).
- `make quality-gate`: passed, including its repeated lint, typecheck, test,
  contract, and security gates.
- `make web-e2e`: passed (78 Playwright cases).
- `make web-a11y`: passed (25 axe cases).
- Two independent review passes found and drove fixes for the pre-scan state
  transition, real ALLOW context, non-safety qualification isolation, durable
  concurrent command replay, database-owned risk classification, and evidence
  allowlisting. Both final re-reviews reported no remaining valid finding.

No changes were pushed or merged and no Issue was closed.
