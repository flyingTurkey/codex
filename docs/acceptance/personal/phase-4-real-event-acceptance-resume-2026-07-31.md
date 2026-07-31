# Phase 4 controlled real Event acceptance — resumed

This is the append-only continuation of Phase 4 on 2026-07-31. The original
`phase-4-real-event-acceptance-2026-07-30.md` remains unchanged with SHA-256
`008F47A9730FBF4D6741D995506BAE1340426CD530FE5A8E68A939371D12BEA4`.
This record does not authorize a formal database write or begin Phase 5.

## Frozen acceptance boundary

- Branch: `codex/phase-4-real-event-acceptance`
- Planned SourceStream key: `cccc-project-briefs`
- Provider/model: `deepseek` / `deepseek-v4-flash`
- Maximum AI cost: `80000` micro-USD
- Live wall limit: `1500` seconds
- Maximum model calls: `8`
- Source requests: `2`
- Schedule attempts: `1`

## Chronological facts

1. The Owner confirmed that a Phase 4 `NO_GO` is not a Phase 5 authorization
   and that any repair must rerun the same document until the complete chain
   passes.
2. Repair `9b6a634e70012a1d6780619227d51bfeb249f75a` made isolated observability
   directory permissions follow the configured `SRBG_DATA_ROOT`. Local
   `make check-fast`, `make check-pr`, and exact-SHA `make check-release`
   passed after the authorized Docker and FlClash restarts.
3. The branch was pushed without opening a pull request. Same-SHA GitHub
   Actions run `30596908480` failed in `migration-test` on a fresh PostgreSQL
   instance because migration `0016` attempted to grant privileges to missing
   role `srbg_publisher_login`.
4. The first confirmed CI blocker was traced to
   `autonomous-content-integration-test` starting only `postgres` and `minio`;
   unlike the reused local data directory, the fresh CI instance had not run
   the existing `role-bootstrap` service.
5. The focused repair makes that one gate wait for `role-bootstrap` before
   running the existing isolated migration verifier. It does not edit
   migrations, bypass grants, alter publication authority, or write a formal
   database.
6. A later local `check-pr` reached `web-a11y` after the repaired migration
   gate and E2E had run, then failed because a single Docker Desktop mount
   visibility probe tried to attach the already attached VHD again. A separate
   bounded repair now checks the system mount, waits up to ten seconds for
   Docker Desktop visibility, and fails closed without a duplicate attach.
7. Candidate `1a0d50ac60096afd0ba5b8ed03f54f98c9de7de4` passed local
   `check-fast`, `check-pr`, its one exact-SHA `check-release`, and same-SHA
   GitHub Actions run `30598821805`.
8. The first isolated live profile
   `srbg-phase4-a275aa5df82d` stopped before any source or model request because
   its fresh PostgreSQL bind mount could not satisfy `initdb` permissions.
   The project containers and network were removed. No document was selected,
   so the same-document replay obligation had not yet begun.
9. A focused diagnostic reproduced PostgreSQL
   `initdb: could not change permissions ... Operation not permitted` on the
   Windows/NTFS bind. The acceptance-only Compose override now uses
   project-scoped named volumes for PostgreSQL, WAL, Redis, and MinIO. A fresh
   diagnostic made all three services healthy and removed all four volumes
   with `down --volumes`.

## Current acceptance state

- SourceStream ID: not generated
- Document ID: not generated
- Model calls: `0`
- Model cost: `0` micro-USD / RMB `0`
- Feed/Reader: not run
- Replay: not run
- Queue/container drain: first live profile containers and network removed;
  no live queue or model task was created
- Decision: `NO_GO` until repair gates, same-SHA remote CI, and the complete
  isolated real-content chain all pass
- Formal database stage: `NOT AUTHORIZED`
