# ADR-0004: Autonomous qualification policy and aggregate replay authority

- Status: Accepted
- Date: 2026-07-21
- Supersedes: the HUMAN_OWNER Gold, semantic human-review, and manual Feed-sampling production-authorization clauses in ADR-0003

## Context

ADR-0003 separated engineering evidence from production authorization but made human semantic review the enduring authority for qualification. The single-Owner product instead needs a replayable policy that can reach a terminal qualification decision without creating an unbounded semantic-review queue. Existing 0046/0047 facts remain historical evidence, including their conflicting authorization record, and cannot be rewritten.

## Decision

Qualification is decided by an immutable `QualificationPolicy` bundle that binds the global rules, SourceStream policy, model provider and model, Prompt, output Schema, code version, and a server-computed SHA-256. The service combines deterministic rules with a Schema-validated AI candidate. Confidence is diagnostic only. A rule/AI conflict may invoke one semantic re-adjudication; an unresolved conflict fails closed as `AUTO_FILTERED`.

`AutomatedDisposition` is the shared terminal/control vocabulary. Technical failures and safety holds are distinct Owner-visible exception classes. Feed suppression is an append-only preference or classification-feedback fact, never publication or source authorization. Offline and shadow evaluations are aggregate-only and are structurally unable to authorize production or affect production state.

The sealed private `.4` corpus is a regression benchmark. Its gate requires relevance and `PrimaryType` to both be correct, precision and recall of at least 90%, no locked-negative leaks, full Schema validity, terminal decisions for the entire corpus, and zero new Owner semantic tasks. Passing that gate qualifies a policy version for later shadow work only; it is not Production GO.

`OWNER_OVERRIDE_GO` remains readable as a historical 0047 fact but grants no authority to this path. New authority can arise only from the autonomous policy gate and later tickets that explicitly connect shadow/runtime consumers.

## Preserved boundaries

- Engineering and Production closeout remain separate.
- Failures close the gate; fixture or CI success cannot be represented as production readiness.
- Real external evidence, public-network safety, robots, terms, rights, budgets, and security controls remain mandatory.
- Worker, SourceAdmission, and PublicationService production read paths are unchanged in Issue #41.
- Private benchmark bodies, URLs, identifiers, labels, and per-case predictions never enter logs, reports, Git, or public artifacts.

## Consequences

0048 expands beside 0046/0047 with immutable policy, decision, exception-event, suppression, evaluation, and shadow facts. Later tickets may consume these frozen contracts without introducing conflicting migrations, but must independently authorize any production-path switch. Rollback is allowed only while 0048 contains no durable facts; otherwise it fails closed to preserve audit history.
