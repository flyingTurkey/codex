# T43 technical exception acceptance

## Scope and authority

Issue #43 adds only the autonomous content technical-failure control plane. It reuses the frozen #41 `AutomatedDisposition`, decision, compensation, Owner exception, and exception-event storage. The additive `0051_technical_exception_recovery` revision is linear from `0050`; it adds only narrow `SECURITY DEFINER` recovery commands and grants Worker function execution rather than direct writes to shared outbox or exception tables. The read projection adds one nullable, bounded `technical_reason_code`; Safety projections require it to remain null.

The slice contains no Safety Hold logic, Owner allow/deny action, Feed suppression, or publication bypass. Disabling a source calls the existing personal source intent API; `desired_enabled=false` remains an Owner preference and does not replace server runtime authorization.

## Retry state machine

`fetch/preparation/queue/model failure -> TECHNICAL_RETRY -> durable wait/lease -> next authoritative attempt`

- Retryable codes are bounded to provider timeout/network/transient availability, temporary database/object-store unavailability, and queue contention. Other technical codes terminate immediately.
- The default bases are 300, 900, and 2700 seconds with full jitter. A controlled jitter of 0.5 proves 150, 450, and 1350 second schedules.
- PostgreSQL `ai_compensation_run_v2` is authoritative. The periodic Worker claims due `PENDING` rows and expired `PROCESSING` leases, so process restart cannot lose work.
- Source acquisition keeps its existing PostgreSQL `fetch_run`/`fetch_schedule` retry authority. Terminal SourceStream failures are projected into the same Owner console; an Owner retry creates a new replay-linked fetch run instead of rewriting the failed attempt history.
- Raw-object loading, deterministic MIME/evidence validation, and queue dispatch are classified before semantic work. Object-store/database/queue outages use the durable compensation path; unsupported MIME, missing immutable evidence, and deterministic validation terminate without unbounded retry. A 15-minute stale-pipeline recovery scan covers a database or broker outage that interrupted failure recording.
- After three scheduled retries, the fourth failed physical attempt appends `TECHNICAL_FAILED` / `TECHNICAL_EXHAUSTED` and moves compensation to `DEAD_LETTER`.
- Owner immediate retry atomically creates a new recovery pipeline and compensation row linked from the immutable failed pipeline. The physical/budget attempt restarts within the new pipeline's frozen 1–4 range while document decision attempts continue to advance globally, preventing reservation reuse, uniqueness conflicts, and false immediate re-exhaustion. An authorized retry event has no arbitrary age expiry, so a multi-day Worker outage cannot invalidate committed recovery intent.
- Adapter callers may lower the retry cap from the default three to any value from zero through three without changing shared storage.
- Repeated callbacks, due claims, Owner commands, queue deliveries, and repeated exhaustion are idempotent. A later `AUTO_ACCEPTED` or `AUTO_FILTERED` decision for the same document lineage automatically resolves the one open technical exception.
- Redis control messages are schema-validated and size-bounded. A malformed message is removed from processing, recorded only with a bounded reason class, and cannot poison later PostgreSQL recovery claims. Each recovery pipeline has distinct physical AI attempt and budget-reservation keys while the immutable decision attempt remains globally monotonic for the document.
- Every accepted Owner retry command advances the exception version. Re-exhaustion advances it again and appends a `TECHNICAL_REEXHAUSTED` system event plus tamper-evident audit record, so stale clients cannot act on changed operational state.

## Owner surface and observability

- `GET /api/v2/owner/exceptions` supports technical kind, open/resolved status, bounded limit, and an exception-ID cursor; detail and optimistic/idempotent command endpoints use the additive safe projection and Problem Details handlers.
- Only safe identifiers, bounded reason codes, attempt/version state, and timestamps are projected. Raw document/model content is not returned.
- `RETRY_REQUESTED` writes an append-only exception event and `OWNER_TECHNICAL_RETRY_REQUESTED` tamper-evident audit record before Redis delivery. Periodic reconciliation republishes committed requests after Redis/process loss, while a Redis set/list transaction prevents duplicate queue entries. The existing audited source API records source disablement.
- Metrics cover retry outcomes/reason class, open technical exception backlog, and Owner commands. `TechnicalRetryExhausted` alerts on terminal failures without high-cardinality labels.
- The Nuxt Owner page provides immediate retry and source disable only. It contains no safety adjudication or suppression control.

## TDD evidence

The controllable-clock integration begins from a real governed SourceStream/raw/document/AI pipeline seam. It proves the three jittered retry times, reconstructs the coordinator to simulate Worker restart, exhausts into `TECHNICAL_FAILED`, projects one Owner exception with its stable technical code, deduplicates a repeated command and audit write, waits two simulated days, creates a linked recovery pipeline through the restricted database command, reserves a fresh physical attempt 1 while recording immutable decision attempt 5, re-exhausts without creating a second current exception, creates another recovery pipeline for decision attempt 6, and auto-resolves after success. A second case proves a non-retryable technical code reaches `TECHNICAL_FAILED` immediately but remains Owner-retryable.

## Verification

- `make lint`: passed (Ruff, design-token validation, UI/Web ESLint).
- `make typecheck`: passed (mypy strict across 153 source files, Vue/Nuxt and generated contract TypeScript checks).
- `make test`: passed (Python 1497 passed / 27 skipped, UI 53 passed, Web 103 passed).
- `make contract-test`: passed (generation reproducibility and 122 contract tests).
- `make security-check`: passed (Python and production JavaScript dependency audit plus Trivy HIGH/CRITICAL secret and misconfiguration scan).
- `make fixture-replay`: passed (374 tests; schema/evidence 100%, unsupported expansion 0, malicious fixtures 6/6 rejected).
- `make quality-gate`: passed, including its repeated lint, typecheck, test, contract, and security checks.
- Isolated PostgreSQL/MinIO seam: 6 passed, including linear `0048 -> 0049 -> 0048 -> 0049 -> 0050 -> 0049 -> 0050 -> 0051 -> 0050 -> 0051` migration replay.
- `make web-e2e`: 76 passed against the dedicated `srbg-issue43` Compose project, including the technical workspace's 200%-equivalent reflow and stable reason-code projection.
- `make web-a11y`: 22 passed against the same dedicated project.
