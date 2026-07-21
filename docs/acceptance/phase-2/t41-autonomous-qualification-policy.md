# T41 autonomous qualification policy acceptance

## Delivered scope

- Versioned `QualificationPolicyIdentity`, `AutomatedDisposition`, decision trace, Owner exception, feed suppression, aggregate evaluation, and shadow-decision contracts.
- Offline/shadow-only adjudication service with deterministic locked-negative rules, untrusted-input prompt, strict AI Schema, evidence/axis checks, and at most one semantic re-adjudication.
- Forward Alembic revision `0048_autonomous_policy_foundation` after the preserved `0046` and `0047` history, including append-only foundations for policy, decisions, exceptions, suppression, aggregate evaluation, and shadow facts.
- Aggregate-only private replay seam and policy-identity-bound resumable candidate cache. The loader verifies the corpus, sealed independent predictions, Owner attempt manifest, and annotation file as one hash chain. Reports and caches exclude document bodies, URLs, case identifiers, labels, and per-case predictions.
- ADR-0004. `OWNER_OVERRIDE_GO` remains historical data and grants no authority to the new path.

## Production-path boundary

Issue #41 does not connect the new service to Worker, `SourceAdmission`, or `PublicationService`. Policy evaluations and shadow decisions explicitly set production authorization/effect to false, and no new Owner semantic task is created.

## TDD evidence

The implementation was driven by failing tests for contract authority exclusions, policy identity hashing, locked-negative boundaries, central-fact precedence, evidence and same-clause equipment-axis invariants, bounded re-adjudication, real provider failure mapping, sealed artifact tampering, private cache minimization, migration history, and aggregate-only replay output. Targeted policy and replay tests pass. Two independent code-review passes and their final focused re-reviews report no remaining P1/P2 findings.

## Private offline replay

The final live aggregate run processed 40 cases with the reviewed policy identity and produced:

- auto accepted: 16
- auto filtered: 24
- technical retry/failed, safety hold, Owner suppressed: 0/0/0/0
- precision: 68.75%
- recall: 55.00%
- locked-negative leaks: 4
- Schema validity: 100.00%
- new Owner semantic tasks: 0
- production authorization: false

The private gate is therefore **NO-GO**. The required 90% precision, 90% recall, zero locked-negative leakage, and 100% Schema validity threshold has not been met. No sample-specific exception was added, and this result must not authorize or switch a production path.

## Verification

- migration head: `0048_autonomous_policy_foundation`
- isolated migration replay: `0047 -> 0048 -> 0047 -> 0048` passed
- `make lint`: passed
- `make typecheck`: passed
- `make contract-test`: passed (122 tests)
- `make security-check`: passed
- `make fixture-replay`: passed (363 tests plus evaluation)
- `make test`: 1443 passed, 27 skipped, 1 pre-existing fixed-point failure in the W0 closeout fixture
- `make quality-gate`: stopped at the same pre-existing W0 test failure after lint and typecheck passed

The private replay failure and inherited W0 test failure remain explicit unfinished acceptance items. This ticket is not eligible for a completion claim or production activation.
