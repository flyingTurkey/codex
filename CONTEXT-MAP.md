# Context Map

## Contexts

- [Acquisition](./docs/contexts/acquisition/CONTEXT.md) — captures compliant source responses before interpretation
- [Intelligence Qualification](./docs/contexts/intelligence-qualification/CONTEXT.md) — decides direct relevance, primary type and review disposition
- [Evidence & AI](./docs/contexts/evidence-ai/CONTEXT.md) — turns evidence into accepted claims, source excerpts and explicitly non-factual AI interpretation
- [Publication & Reader Projection](./docs/contexts/publication-reader/CONTEXT.md) — grants visibility and presents a reader-first Event projection

## Relationships

- **Acquisition → Intelligence Qualification**: supplies immutable raw responses, parsed blocks and source metadata; it does not create visible Events.
- **Intelligence Qualification → Evidence & AI**: only a relevant qualification may authorize candidate-fact extraction.
- **Evidence & AI → Publication & Reader Projection**: supplies active accepted claims, evidence-linked excerpts and versioned AI summary state.
- **Publication & Reader Projection → Intelligence Qualification**: Owner corrections request re-evaluation; they never write publication state directly.

## Cross-context decisions

- [ADR-0002](./docs/adr/0002-api-v2-empty-projection-cutover.md) freezes the v1/v2 generation boundary and empty v2 projection cutover.
- [ADR-0003](./docs/adr/0003-intelligence-v2-closeout-profiles.md) separates engineering closeout from production readiness without weakening publication or safety boundaries.
