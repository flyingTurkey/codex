# T46 Champion/Challenger policy optimization acceptance

Issue #46 implements the policy lifecycle under parent Spec #40. It builds on
the merged #43 technical exception, #44 Feed suppression, and #45 Safety hold
control planes. It does not add Owner semantic classification work or grant
replay/shadow facts production authority.

## Preconditions and isolation

- Fetched `origin --prune` before worktree creation.
- Based `codex/issue-46-policy-optimization` on remote integration commit
  `867c8c3f999c02a60ca02272d75f1ab59a60b066`.
- Verified the #43 merge `1c2a170`, #44 merge `6d6d373`, and #45 merge
  `867c8c3` are ancestors of `origin/codex/issue-40-integration`.
- Created the clean independent worktree
  `D:\CodexProjects\srbg-intelligence-platform-issue-46`.
- Confirmed one Alembic head and dynamically extended
  `0053_safety_exception_lifecycle` with `0054_policy_optimization`.
- Used the isolated Compose project `srbg-issue46` with PostgreSQL `55446`,
  Redis `56446`, MinIO `59450`, and MinIO console `59451`; its persistent data
  root is distinct from Issue #45.

## Delivered behavior

- Every new source-content LIVE run and fixed SHADOW canary stores a
  `policy_bundle_id` at creation. Normal callbacks, physical retry, semantic
  recheck, canary callback, and technical recovery load or copy that exact
  bundle. They do not re-read the active pointer.
- The exact ADR-0005 baseline bootstraps through a restricted database command.
  `PROMOTE` and `ROLLBACK` append to
  `qualification_policy_activation_v2`; the active pointer is the derived
  `active_qualification_policy_v2` view. No historical bundle, decision,
  evaluation, shadow decision/window, health window, or activation is updated.
- Private replay can append aggregate evaluation plus invariant facts. Its
  `authorizes_production` value is always false. A complete offline pass grants
  only eligibility for Challenger SHADOW work.
- The scheduled policy shadow selects an offline-qualified Challenger when one
  exists, loads the bound document's real hash-verified bytes, and classifies
  the same normalized input as the Champion. The fixed synthetic provider probe
  remains separate and never contributes promotion evidence. SHADOW decisions
  remain `affects_production=false` and terminalize before Item, accepted claim,
  Event, PublicationService, or Feed materialization.
- The lifecycle monitor requires at least 20 distinct document versions with
  terminal shadow decisions and one
  aggregate window. It compares Challenger and Champion decisions and enforces
  stability, technical exception, Safety hold, suppression, category drift,
  Schema, hard-negative, authority, evidence, projection, and zero Owner
  semantic-task gates. One-document or placeholder precision/recall records
  cannot promote.
- After promotion, append-only health windows monitor actual FULL publication
  yield, active suppression and authoritative budget facts alongside technical
  exceptions, Safety holds, suppression, Schema/projection failures,
  hard-negative leaks, cost-budget failure, and category drift. A hard failure
  or bounded-rate regression after at least 20 runs automatically appends one
  idempotent rollback to the previous Champion.
- Low-cardinality metrics and alerts report shadow-window rejection,
  promotion, healthy rollback checks, and applied rollback without source,
  document, policy hash, or private benchmark labels.

## Highest-seam evidence

The single existing `t41_autonomous_content_integration.py` highest seam still
starts at the governed personal SourceStream and covers automatic Feed,
automatic filtering, technical retry/exhaustion/recovery, Safety hard blocks,
suppression/restoration, and zero Owner semantic classification cases. Issue
#46 extends that same file—rather than creating a second top-level harness—to
prove:

- the source handoff atomically binds the initial Champion;
- a complete offline plus aggregate SHADOW window promotes a Challenger;
- the already-created LIVE run still hydrates the original Champion;
- a production regression appends rollback and restores the previous active
  pointer; and
- every evaluation/shadow fact remains non-authorizing/non-production while
  Owner semantic-task count stays zero.

The full isolated seam passed 9/9 against real PostgreSQL and private MinIO with
only the documented deterministic network/model edges.

## Honest status

- `MECHANISM_ENGINEERING`: complete for Issue #46.
- `CHALLENGER_PROMOTION`: mechanism verified with deterministic acceptance
  evidence; no claim is made that a real production Challenger has passed.
- `PRODUCTION_CLOSEOUT`: not claimed. This ticket did not create real-source,
  real-DeepSeek, real Feed-sampling, or production-window evidence.
- Historical `.4`: remains 70% precision, 70% recall, five locked-negative
  leaks, and **NO-GO** against its original threshold. It was not rewritten,
  threshold-reduced, or represented as a pass.

## Verification

- Isolated migration replay:
  `0048 -> 0049 -> 0048 -> 0049 -> 0050 -> 0049 -> 0050 -> 0051 -> 0050 -> 0051 -> 0052 -> 0051 -> 0052 -> 0053 -> 0052 -> 0053 -> 0054 -> 0053 -> 0054`
  passed.
- Focused policy, migration, Worker, bridge, and orchestration tests: passed.
- Full highest SourceStream seam: 9 passed.
- Lint recipes: Ruff, token generation check, UI ESLint, and Web ESLint passed.
- Typecheck recipes: mypy strict, UI `vue-tsc`, Nuxt typecheck, and generated
  contract TypeScript check passed.
- Test recipes: Python 1550 passed / 27 skipped, UI 53 passed, and Web 106
  passed. The skips are the repository's existing environment-gated suites.
- Contract gate: generated contracts were reproducible and 123 tests passed.
- Security gate: `pip-audit`, production `pnpm audit`, Trivy secret scan, and
  Trivy HIGH/CRITICAL misconfiguration scan passed with no findings.
- Fixture replay: 377 tests and the Round 09 evaluator passed.
- Production-build browser gates: Web E2E 78 passed and Web a11y 25 passed.
- `quality-gate` is exactly the lint, typecheck, test, contract, and security
  dependencies above; every constituent Makefile recipe passed. The Windows
  executor had no GNU Make frontend, so the recipes were invoked directly
  without changing commands, thresholds, or test selection.
- After the final review fixes, the full isolated seam and migration replay
  passed together: migration `0054 -> 0053 -> 0054` remained reversible and all
  9 integration cases passed in 9.82 seconds.
- Independent code-review passes identified and closed distinct-document,
  real-input shadow, causal projection, runtime identity, real health-fact,
  ledger-ordering, idempotency, and invariant-reporting defects. The final
  code-quality and Spec reviewers both reported no remaining valid findings.

No changes were pushed or merged and parent Spec #40 was not closed.
