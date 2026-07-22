# ADR-0005: Autonomous content qualification production switch

- Status: Accepted
- Date: 2026-07-22
- Extends: ADR-0004

## Context

The product has one Owner and must continue researching without semantic approval work. The Owner amended Issue #41 to absorb the content-production loop from Issue #42. The private `.4` replay remains useful diagnostic evidence, but its historical threshold is a reminder rather than production authority or a global blocker.

## Decision

The real content Worker uses the immutable `qualification-policy-2.2.0` bundle after raw-first storage, current-version validation, SourceAdmission, public-network safety, security and budget authorization. Its rule, Prompt `autonomous-classify-2.7.0`, and Schema `autonomous-classify-output-2.0.0` identities match the frozen replay seam. Deterministic exclusions run before the model. Other candidates use the strict autonomous Prompt and Schema; a rule/AI conflict receives exactly one semantic recheck. Every terminal result is appended to `automated_qualification_decision_v2` with the exact policy identity. New runs do not read Owner Gold and `OWNER_OVERRIDE_GO` cannot authorize them.

`AUTO_FILTERED` terminates before Item, Event, accepted claim, excerpt or publication materialization. Raw content, the document version, hash, model steps and decision trace remain private and auditable. It creates no Owner semantic task. `AUTO_ACCEPTED` may continue through extraction and the automatic evidence gate. Only accepted claims with bidirectional evidence may form `SourceExcerpt`; `PublicationService`, using current PostgreSQL facts, remains the sole Feed/search/hotspot/Event projection writer. These records are `human_reviewed=false` and are presented as machine-organized content.

Hard public-network, access-control, malicious-file, credential and explicit legal prohibitions remain non-bypassable. SourceAdmission pauses on an explicit robots, terms or copyright prohibition, but permits bounded collection when those facts are missing or ambiguous; HUMAN_OWNER Gold and soft-yield observations grant no admission authority. Rate, budget, timeout and circuit-breaker failures pause or retry through the existing technical path rather than becoming semantic rejection. Operational exception UX, suppression UX and policy optimization remain Issues #43–#46.

## Consequences

Migration `0049_autonomous_content_switch` follows 0048, registers the production Prompt/Schema, preserves `INDUSTRY_UPDATE` as an independent compatibility storage type/channel, and grants the Worker only append access to policy and decision facts. 0046/0047 remain unchanged history. Rollback from 0049 is allowed only before the production policy has durable decisions or industry rows; otherwise it fails closed. A new document version receives a new decision and the existing invalidation/outbox path withdraws stale claims and projections.
