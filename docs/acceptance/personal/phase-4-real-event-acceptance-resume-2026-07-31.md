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
10. Candidate `444a31b2d6a30ae7e2a1cde322d9f18dc7583ff3` passed local
    `check-fast`, full `check-pr`, its one exact-SHA `check-release`, and
    same-SHA GitHub Actions run `30599938104`. Its live profile
    `srbg-phase4-6b43c5a2ff1e` made PostgreSQL, Redis, and MinIO healthy, then
    stopped at the first confirmed blocker while migrating the fresh database:
    migration `0016` could not grant to missing role `srbg_publisher_login`.
    The runner had not invoked the existing `role-bootstrap` service. No source
    request, document selection, model call, queue task, or publication
    occurred. Cleanup removed all scoped containers, four named volumes, and
    the network.
11. The focused repair adds the missing role bootstrap between infrastructure
    readiness and the unchanged migration verifier. A regression test first
    reproduced the missing step and then passed. The repair does not edit a
    migration, weaken an ACL, create a publication, or touch the formal
    database.
12. Repair candidate `d367f92fef010bd18f0a62517685a8447c0d098a` passed
    `check-fast`, full `check-pr`, its one exact-SHA `check-release`, and
    same-SHA GitHub Actions run `30601429684`. A first `check-pr` attempt was
    invalidated when Docker Desktop rebuilt the runtime during Playwright and
    pages returned `ERR_CONNECTION_REFUSED`; after the authorized Docker
    restart, the unchanged SHA passed the complete gate.
13. Live profile `srbg-phase4-410842f04a73` passed role bootstrap and the full
    `0054 -> 0055 -> 0054 -> 0055` migration replay, then stopped before any
    public-network request because the acceptance seed attempted to store
    `www.ccccltd.cn/news/jcxw/jx/` in the host-only
    `source_stream.authorization_boundary`. PostgreSQL correctly rejected it
    with `ck_source_stream_boundary`. Evidence file
    `.cache/phase4-evidence/d367f92fef010bd18f0a62517685a8447c0d098a.json`
    records `NO_GO`, zero model calls, and a drained queue. Cleanup removed all
    scoped containers, four named volumes, and the network.
14. The focused repair keeps `www.ccccltd.cn` in the host authority field and
    retains `/news/jcxw/jx/` in the existing controlled-run `path_prefix`.
    A regression test first reproduced and then closed this schema-field
    mismatch. No source admission, robots, terms, rate, budget, publication,
    or formal-database boundary was changed.
15. Repair candidate `6e4e84a0e1c684717867cdac1a298a7757cf89f1`
    passed `check-fast`, full `check-pr`, its one exact-SHA `check-release`, and
    same-SHA GitHub Actions run `30602544512`. An earlier unchanged-SHA
    `check-pr` stopped at `web-a11y` when the WSL backend returned
    `Wsl/Service/0x8007274c`; after the authorized Docker restart restored the
    mounted data root, the full gate passed.
16. Live profiles `srbg-phase4-48223f725efb` and
    `srbg-phase4-8167d08d7873` each passed fresh-database bootstrap, migration
    replay, SourceAdmission, fixed budget and deadline setup, then made the
    bounded list request to `https://www.ccccltd.cn/news/jcxw/jx/`. The source
    returned HTTP `521` both before and after the authorized FlClash restart.
    Each run stopped before discovery, raw-object persistence, document
    selection, or any model call. No alternate route, second source, access
    control bypass, or increased budget was attempted.
17. The latest evidence file records SourceStream ID
    `019fb785-8785-70d5-921c-10c8bc029549`, controlled run
    `019fb785-87a5-7ac2-9a04-a6202a0eac76`, fetch run
    `019fb785-87fa-7cdd-8654-81b4b7881075`, zero discovered/fetched documents,
    one failed fetch, zero model calls, and blocker
    `BOUNDED_SOURCE_FETCH_FAILED`. The stop path then hit the existing
    `manual source disable has priority` protection, so database-level drain
    was not recorded. Runner teardown nevertheless removed all scoped
    containers, four named volumes, and the network. This is still `NO_GO`.
18. The Owner authorized continuation to close the documented blockers and
    complete Phase 4, without automatically starting the next phase. Three
    acceptance-integrity regressions were reproduced before implementation:
    same-SHA reruns reused one evidence filename; SourceStream UUID was not
    fixed across fresh runs; and failure teardown mixed a personal manual
    disable with a still-running controlled source. The focused repair gives
    each run a unique evidence filename and exclusive-create writer, pins
    SourceStream ID `019fb785-8785-70d5-921c-10c8bc029549` before network I/O,
    and closes runtime authority through a deterministic disabled owner intent
    before pausing the schedule and stopping the isolated source. It does not
    edit SourceAdmission, robots, terms, rate, budget, publication, or formal
    database rules. All three focused tests and the complete foundation file
    pass; no new public-network or model request was made during this repair.

## Current acceptance state

- SourceStream ID: `019fb785-8785-70d5-921c-10c8bc029549` (latest isolated run)
- Document ID: not generated
- Model calls: `0`
- Model cost: `0` micro-USD / RMB `0`
- Feed/Reader: not run
- Replay: not run
- Queue/container drain: runner teardown removed the latest profile's scoped
  containers, network, and all four named volumes with zero residual Docker
  resources; database-level queue drain is **not proven** because the stop path
  raised before writing that evidence
- Decision: `NO_GO` until repair gates, same-SHA remote CI, and the complete
  isolated real-content chain all pass
- Formal database stage: `NOT AUTHORIZED`

## Continuation result at candidate `44aafabc` (append-only)

19. Repair candidate `44aafabc7d827d4d0d8caf3cecd8876003c94731`
    passed `check-fast`, full `check-pr`, its one exact-SHA `check-release`, and
    same-SHA GitHub Actions run `30622910103`. Live profile
    `srbg-phase4-8014e1b372f9` passed fresh role bootstrap, the full
    `0054 -> 0055 -> 0054 -> 0055` migration replay, SourceAdmission, and the
    frozen budget/deadline setup. Its single bounded list fetch to
    `https://www.ccccltd.cn/news/jcxw/jx/` again received HTTP `521`. The run
    stopped at `BOUNDED_SOURCE_FETCH_FAILED` before discovery, raw-object
    persistence, document selection, or model use. Unique evidence file
    `.cache/phase4-evidence/44aafabc7d827d4d0d8caf3cecd8876003c94731-8014e1b372f9.json`
    records fixed SourceStream ID `019fb785-8785-70d5-921c-10c8bc029549`,
    controlled run `019fb7ae-aaee-7432-82f6-f95341241a3a`, fetch run
    `019fb7ae-ab61-7d0b-a526-14dcc2f3c722`, zero discovered/fetched documents,
    zero model calls, and zero model cost. The repaired stop path records
    `active_database_tasks=0`, `redis_keys=0`, and `drained=true`; teardown
    removed every scoped container, all four named volumes, and the network.
    No alternate route, second source, access-control bypass, direct SQL
    publication, or increased budget was attempted.

### Latest acceptance state

- RELEASE_CANDIDATE_SHA: `44aafabc7d827d4d0d8caf3cecd8876003c94731`
- SourceStream ID: `019fb785-8785-70d5-921c-10c8bc029549`
- Document ID: not generated; the source failed before discovery
- Model calls and cost: `0`; `0` micro-USD / RMB `0`
- Full chain: stopped at list fetch with HTTP `521`; raw object through Reader
  did not run
- Feed/Reader: not generated / not run
- Replay: not run because no document or publication existed
- Queue/resource drain: `PASS` (`0` active database tasks, `0` Redis keys,
  no scoped Docker containers, volumes, or network)
- Decision: `NO_GO`
- Formal database stage: `NOT AUTHORIZED`; Phase 5 remains unstarted
