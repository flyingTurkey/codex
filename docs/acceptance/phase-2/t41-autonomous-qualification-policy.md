# T41 autonomous qualification policy acceptance

## Delivered scope

- Versioned `QualificationPolicyIdentity`, `AutomatedDisposition`, decision trace, Owner exception, feed suppression, aggregate evaluation, and shadow-decision contracts.
- Offline/shadow-only adjudication service with deterministic locked-negative rules, untrusted-input prompt, strict AI Schema, evidence/axis checks, and at most one corrective semantic re-adjudication for a failed or conflicting candidate.
- Forward Alembic revision `0048_autonomous_policy_foundation` after the preserved `0046` and `0047` history, including append-only foundations for policy, attempt-keyed retry/final decisions, exceptions, suppression, aggregate evaluation, and shadow facts.
- Aggregate-only private replay seam. The loader verifies the corpus, sealed independent predictions, Owner attempt manifest, annotation file, unique case identifiers, and recorded response artifact as one hash chain. Live candidates and exact decision traces remain process-local; no cache, report, or log persists document bodies, URLs, case identifiers, labels, or per-case predictions. Live invocation audit requires an exclusive-create `--audit-output` beneath `SRBG_DATA_ROOT` and persists only version bindings, input/output hashes, latency, Token counts, provider cost when supplied, and a manifest hash.
- ADR-0004. `OWNER_OVERRIDE_GO` remains historical data and grants no authority to the new path.

## Production-path boundary

Issue #41 does not connect the new service to Worker, `SourceAdmission`, or `PublicationService`. Policy evaluations and shadow decisions explicitly set production authorization/effect to false, and no new Owner semantic task is created.

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

The private gate is therefore **NO-GO**. The required 90% precision, 90% recall, zero locked-negative leakage, and 100% Schema validity threshold has not been met. Expanded Owner authority was used to evaluate higher-capability thinking and non-thinking profiles, structured central-fact extraction, bounded lead projection, and adversarial verification. All produced worse aggregate quality than the reviewed Flash baseline and were removed. No sample-specific exception, threshold reduction, frozen-artifact change, or best-of-run selection was used. This result must not authorize or switch a production path.

## Verification

- migration head: `0048_autonomous_policy_foundation`
- isolated migration replay: `0047 -> 0048 -> 0047 -> 0048` passed
- `make lint`: passed
- `make typecheck`: passed
- `make contract-test`: passed (122 tests)
- `make security-check`: passed
- `make fixture-replay`: passed (363 tests plus evaluation)
- inherited W0 closeout mismatch: fixed by aligning its stale 20/10/10 fixture and validator with the frozen 20/0/20 annotation Schema; the focused regression passes
- `make lint`: passed
- `make typecheck`: passed (mypy strict: 150 source files; Nuxt/UI/contract TypeScript passed)
- `make test`: passed (Python 1464 passed, 27 skipped; UI 53 passed; Web 101 passed)
- `make contract-test`: passed (122 tests; generated contracts reproducible)
- `make security-check`: passed (dependency audits and HIGH/CRITICAL secret/misconfiguration scan)
- `make fixture-replay`: passed (371 tests plus evaluation)
- `make quality-gate`: passed

Code review resolved the safety-precedence, Prompt/Schema identity-binding, retry-convergence, model-call audit, and private input-size findings. The W0 20/0/20 closeout reconciliation remains because the frozen Owner Gold annotation Schema permits only `POSITIVE` and `NEGATIVE`; restoring the stale `BOUNDARY` distribution makes the inherited closeout regression fail.

The private replay quality failure remains an explicit unfinished acceptance item. This ticket is not eligible for a completion claim or production activation.
