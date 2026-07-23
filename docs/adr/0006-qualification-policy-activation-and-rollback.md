# ADR-0006: Qualification policy activation and automatic rollback

- Status: Accepted
- Date: 2026-07-23
- Extends: ADR-0004 and ADR-0005

## Context

ADR-0004 made policy bundles, evaluations, and shadow decisions immutable and
non-authorizing. ADR-0005 connected one fixed server policy to production. Issue
#46 needs policy improvement without changing an in-flight run, rewriting the
historical `.4` NO-GO, or turning replay/shadow evidence into publication
authority.

## Decision

Every `ai_pipeline_run` created after migration 0054 stores a
`policy_bundle_id`. The source-content handoff selects the active bundle inside
the same database transaction that creates the run. Callbacks, retries,
semantic rechecks, canaries, and technical recovery load or copy that stored
identifier. A later activation therefore affects only later runs.

Policy lifecycle state uses an independent append-only activation ledger.
`active_qualification_policy_v2` is a derived pointer to the latest activation
for one SourceStream policy version. `BOOTSTRAP` is restricted to the exact
ADR-0005 baseline. `PROMOTE` requires both:

- a complete private `OFFLINE_REPLAY` aggregate with precision and recall at
  least 90%, zero locked-negative, authority, evidence, projection, and Owner
  semantic-task violations, and `authorizes_production=false`; and
- at least 20 terminal Challenger shadow decisions for distinct document
  versions, each reduced to its latest terminal fact and aggregated against the
  current Champion, with at least 90% decision stability, bounded technical,
  safety, suppression, and category drift, zero invariant failures, and
  `affects_production=false`.

The fixed canary selects an eligible offline-qualified Challenger for SHADOW
execution. It terminates before Item, claim, Event, or reader materialization.
A one-minute lifecycle task aggregates new shadow windows and promotes only
when both gates pass.

After promotion, append-only production health windows measure actual FULL
publication yield, active Feed suppression, authoritative budget facts,
technical exceptions, safety holds, suppression, Schema/projection failures,
hard-negative leakage, cost-budget failure, and category drift. A hard failure
or bounded-rate regression with at least 20 runs appends one idempotent
`ROLLBACK` activation pointing to the previous Champion. It never mutates a
bundle, decision, evaluation, shadow fact, or earlier activation.

## Authority boundaries

`qualification_policy_evaluation_v2.authorizes_production` remains permanently
false. Shadow facts and aggregate windows remain permanently
`affects_production=false`. They are evidence checked by the server activation
command, not production actions themselves. `PublicationService` remains the
only reader-projection writer, and SourceAdmission remains independent.

The historical `.4` result remains 70% precision, 70% recall, five locked
negative leaks, and NO-GO against its original threshold. It is neither
rewritten nor treated as a global production blocker. Engineering completion,
an individual Challenger promotion outcome, and `PRODUCTION_CLOSEOUT` are
separate statuses.

## Consequences

Migration `0054_policy_optimization` is linear after 0053. Downgrade is allowed
only before any activation, invariant, shadow-window, health, or run-binding
fact exists. Metrics and alerts expose bounded promotion rejection and
automatic rollback outcomes without document, source, policy hash, or private
benchmark labels.
