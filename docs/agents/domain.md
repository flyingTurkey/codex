# Domain Docs

This repository uses a multi-context domain documentation layout.

## Before exploring

Read:

- `CONTEXT-MAP.md` at the repository root, if it exists;
- each context-specific `CONTEXT.md` referenced by the map and relevant to the
  task;
- system-wide ADRs under `docs/adr/`;
- context-specific ADRs referenced by the relevant context documentation.

If these files do not exist yet, proceed silently. Do not invent them merely to
fill the layout. `/domain-modeling`, usually reached through
`/grill-with-docs`, creates them lazily when terminology or decisions are
actually resolved.

## Layout

```text
/
├── CONTEXT-MAP.md
├── docs/
│   └── adr/                    # System-wide decisions
├── apps/
│   ├── web/
│   │   └── CONTEXT.md         # Created only when needed
│   ├── api/
│   │   └── CONTEXT.md
│   └── worker/
│       └── CONTEXT.md
└── packages/
    ├── contracts/
    │   └── CONTEXT.md
    └── ui/
        └── CONTEXT.md
```

The map is authoritative. A package does not require a `CONTEXT.md` merely
because it exists, and a business context does not have to match a technical
package one-to-one.

## Use the glossary vocabulary

When naming a domain concept in an issue, proposal, hypothesis, test, API, or
model, use the term defined by the relevant `CONTEXT.md`.

If a needed concept is absent, reconsider whether new terminology is actually
necessary. Genuine gaps should be resolved through `/domain-modeling`.

## Flag ADR conflicts

If proposed work contradicts an existing ADR, state the conflict explicitly
instead of silently overriding the decision.
