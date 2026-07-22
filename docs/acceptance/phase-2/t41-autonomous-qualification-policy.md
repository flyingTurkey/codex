# T41 autonomous qualification policy acceptance

## 2026-07-22 Owner amendment and absorbed T02 closeout

The Owner amended #41 after the original offline foundation: the `.4` benchmark is a non-authorizing reminder rather than a global blocker, and #41 absorbs only #42/T02's production content loop. Issues #43–#46 remain independent. The accepted production seam is:

`authorized SourceStream -> raw/document version -> versioned autonomous decision -> accepted claims/evidence/SourceExcerpt -> PublicationService -> Feed`

- Worker preserves source-content bridge runs as `LIVE` across every callback, evaluates deterministic exclusions before dispatching the model, uses the exact shared versioned Prompt/Schema, permits one semantic recheck, and atomically appends the policy identity and terminal decision. `SHADOW` results are saved only in `affects_production=false` evaluation/shadow tables and terminate before Item, claim or Feed materialization.
- New runs contain no Owner Gold lookup or `OWNER_OVERRIDE_GO` authorization branch.
- `AUTO_FILTERED` retains private raw/document/hash/model/decision history but terminates before Item/Event, accepted claim, search, hotspot or Event projection creation and creates no Owner semantic task.
- `AUTO_ACCEPTED` is permission to continue evidence processing, not model publication authority. Automatic evidence facts, accepted claims and SourceExcerpt remain required; only `PublicationService` can materialize the reader projection. The result remains `human_reviewed=false`/machine-organized.
- The authoritative SourceAdmission assessment writer and closeout verifier no longer read HUMAN_OWNER Gold. Explicit public-network, robots, terms or copyright prohibitions pause the source; missing legal metadata, soft-yield observations and qualification leakage permit bounded admission and remain observable policy-iteration signals rather than collection vetoes.
- `INDUSTRY_UPDATE` remains independent through compatibility Item/channel/Event storage and the v2 projection; it is not coerced into the digital category.
- New document versions are separately adjudicated; existing candidate invalidation and durable publisher outboxes remove stale claims and projections.
- Forward migration `0049_autonomous_content_switch` registers the production Prompt/Schema and Worker append grants after 0048. 0046/0047 are unchanged.
- ADR-0005 records the production switch. Source discovery/admission continues to use server public-network, access-control, explicit legal, rate and budget controls; no model output grants source or publication authority.

## Delivered scope

- Versioned `QualificationPolicyIdentity`, `AutomatedDisposition`, decision trace, Owner exception, feed suppression, aggregate evaluation, and shadow-decision contracts.
- Shared offline/shadow/production adjudication service with deterministic locked-negative rules, untrusted-input Prompt, strict AI Schema, evidence/axis checks, and at most one corrective semantic re-adjudication for a failed or conflicting candidate.
- Forward Alembic revision `0048_autonomous_policy_foundation` after the preserved `0046` and `0047` history, including append-only foundations for policy, attempt-keyed retry/final decisions, exceptions, suppression, aggregate evaluation, and shadow facts.
- Aggregate-only private replay seam. The loader verifies the corpus, sealed independent predictions, Owner attempt manifest, annotation file, unique case identifiers, and recorded response artifact as one hash chain. Live candidates and exact decision traces remain process-local; no cache, report, or log persists document bodies, URLs, case identifiers, labels, or per-case predictions. Live invocation audit requires an exclusive-create `--audit-output` beneath `SRBG_DATA_ROOT` and persists only version bindings, input/output hashes, latency, Token counts, provider cost when supplied, and a manifest hash.
- ADR-0004. `OWNER_OVERRIDE_GO` remains historical data and grants no authority to the new path.

## Original production-path boundary (superseded by the Owner amendment above)

The earlier restriction against connecting Worker/SourceAdmission/PublicationService no longer applies to #41. Offline evaluations and shadow decisions still cannot authorize or affect production; the production authority is the current server policy and authoritative database context described in ADR-0005.

## TDD evidence

The implementation was driven by failing tests for contract authority exclusions, policy identity hashing (including actual Prompt and output Schema bytes), locked-negative boundaries, central-fact precedence, evidence and same-clause equipment-axis invariants, common lifecycle-bound machinery vocabulary, bounded re-adjudication, safety-signal precedence on both attempts, bilingual final verification, real provider failure mapping, sealed artifact tampering, duplicate identifiers, oversized private artifacts, process-local private traces, migration history, and aggregate-only replay output. Targeted policy and replay tests pass.

## Private offline replay

The final live aggregate run processed 40 cases with `qualification-policy-2.2.0` and produced:

- auto accepted: 20
- auto filtered: 20
- technical retry/failed, safety hold, Owner suppressed: 0/0/0/0
- precision: 70.00%
- recall: 70.00%
- locked-negative leaks: 5
- Schema validity: 100.00%
- new Owner semantic tasks: 0
- production authorization: false

The historical private gate result is therefore **NO-GO against its original threshold**. It remains diagnostic and does not authorize production. Under the 2026-07-22 Owner amendment it is also not a global completion blocker; production authority comes only from the server-controlled policy/runtime/publication gates. No sample-specific exception, threshold reduction, frozen-artifact change, or best-of-run selection was used.

## Verification

- migration head after the production amendment: `0049_autonomous_content_switch`
- isolated migration replay: `0048 -> 0049 -> 0048 -> 0049` passed
- inherited W0 closeout mismatch: fixed by aligning its stale 20/10/10 fixture and validator with the frozen 20/0/20 annotation Schema; the focused regression passes
- `make lint`: passed
- `make typecheck`: passed (mypy strict: 150 source files; Nuxt/UI/contract TypeScript passed)
- `make test`: passed (Python 1481 passed, 27 skipped; UI 53 passed; Web 101 passed)
- `make contract-test`: passed (122 tests; generated contracts reproducible)
- `make security-check`: passed (dependency audits and HIGH/CRITICAL secret/misconfiguration scan)
- `make fixture-replay`: passed (374 tests plus evaluation)
- isolated PostgreSQL/Redis/object-storage integration: passed (2 tests: duplicate deterministic filtering remained idempotent with no Item/task/model call; a governed PRODUCTION raw capture and WAITING_AI handoff entered through the real Worker authorization seam, then automatic industry acceptance created evidence-backed claims and SourceExcerpt, traversed the durable publisher outbox, and produced a FULL `/api/v2` reader projection with `human_reviewed=false` and no Owner semantic case)
- `make quality-gate`: passed (including the full test, contract, dependency and HIGH/CRITICAL security scan sequence)
- CI environment regression: GNU Make now assigns `SRBG_EXTERNAL_IO_TIMEOUT_SECONDS` before exporting it; the focused infrastructure suite passes (19 tests), preventing an empty timeout from aborting test collection on clean runners.
- CI integration isolation: the integration job creates and exports a runner-scoped ephemeral `SRBG_DATA_ROOT`, with service-specific UID/GID and permissions, before Compose startup; production and local data-root requirements remain unchanged.
- Clean-database startup: an idempotent no-password login-role bootstrap now runs after PostgreSQL health and before Alembic; the existing post-migration initializer still assigns passwords and memberships. This preserves all historical migration files while allowing their grants to execute from an empty database.
- Runtime asset boundary: `.dockerignore` admits only the authoritative autonomous classification Schema needed by migration 0049; the rest of the repository-only documentation remains excluded from application images.

Code review resolved the safety-precedence, Prompt/Schema identity-binding, retry-convergence, model-call audit, private input-size, LIVE-to-SHADOW mutation, LIVE callback authorization, SourceAdmission writer/leakage veto, production/replay Prompt divergence, and SHADOW fact-separation findings. The W0 20/0/20 closeout reconciliation remains because the frozen Owner Gold annotation Schema permits only `POSITIVE` and `NEGATIVE`; restoring the stale `BOUNDARY` distribution makes the inherited closeout regression fail.

The private replay quality shortfall remains explicitly recorded and must not be described as a pass. Per the Owner amendment it is a reminder, not an unfinished #41 acceptance item.
