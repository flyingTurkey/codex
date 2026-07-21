# T41 autonomous qualification policy acceptance

## Delivered scope

- Versioned `QualificationPolicyIdentity`, `AutomatedDisposition`, decision trace, Owner exception, feed suppression, aggregate evaluation, and shadow-decision contracts.
- Offline/shadow-only adjudication service with deterministic locked-negative rules, untrusted-input prompt, strict AI Schema, evidence/axis checks, and at most one corrective semantic re-adjudication for a failed or conflicting candidate.
- Forward Alembic revision `0048_autonomous_policy_foundation` after the preserved `0046` and `0047` history, including append-only foundations for policy, decisions, exceptions, suppression, aggregate evaluation, and shadow facts.
- Aggregate-only private replay seam. The loader verifies the corpus, sealed independent predictions, Owner attempt manifest, annotation file, unique case identifiers, and recorded response artifact as one hash chain. Live candidates and exact decision traces remain process-local; no cache, report, or log persists document bodies, URLs, case identifiers, labels, or per-case predictions.
- ADR-0004. `OWNER_OVERRIDE_GO` remains historical data and grants no authority to the new path.

## Production-path boundary

Issue #41 does not connect the new service to Worker, `SourceAdmission`, or `PublicationService`. Policy evaluations and shadow decisions explicitly set production authorization/effect to false, and no new Owner semantic task is created.

## TDD evidence

The implementation was driven by failing tests for contract authority exclusions, policy identity hashing, locked-negative boundaries, central-fact precedence, evidence and same-clause equipment-axis invariants, common lifecycle-bound machinery vocabulary, bounded re-adjudication, bilingual final verification, real provider failure mapping, sealed artifact tampering and duplicate identifiers, process-local private traces, migration history, and aggregate-only replay output. Targeted policy and replay tests pass.

## Private offline replay

The final live aggregate run processed 40 cases with the reviewed policy identity and produced:

- auto accepted: 19
- auto filtered: 21
- technical retry/failed, safety hold, Owner suppressed: 0/0/0/0
- precision: 73.68%
- recall: 70.00%
- locked-negative leaks: 4
- Schema validity: 100.00%
- new Owner semantic tasks: 0
- production authorization: false

The private gate is therefore **NO-GO**. The required 90% precision, 90% recall, zero locked-negative leakage, and 100% Schema validity threshold has not been met. Aggregate diagnosis found no label-independent rule that could remove all leaked negatives while recovering the remaining relevance, primary-type, axis, and evidence disagreements. No sample-specific exception was added. Changing the fixed model profile, benchmark, or model topology requires authority outside Issue #41, and this result must not authorize or switch a production path.

## Verification

- migration head: `0048_autonomous_policy_foundation`
- isolated migration replay: `0047 -> 0048 -> 0047 -> 0048` passed
- `make lint`: passed
- `make typecheck`: passed
- `make contract-test`: passed (122 tests)
- `make security-check`: passed
- `make fixture-replay`: passed (363 tests plus evaluation)
- `make test`: 1452 passed, 27 skipped, 1 pre-existing fixed-point failure in the W0 closeout fixture
- `make quality-gate`: stopped at the same pre-existing W0 test failure after lint and typecheck passed

The private replay failure and inherited W0 test failure remain explicit unfinished acceptance items. This ticket is not eligible for a completion claim or production activation.
