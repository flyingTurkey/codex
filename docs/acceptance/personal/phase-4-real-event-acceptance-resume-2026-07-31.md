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

28. The Owner explicitly authorized abandoning the repeatedly unavailable CCCC
    SourceStream and selecting one compliant replacement without starting Phase
    5. Point-in-time research first rejected Sichuan Transport, CSCEC, and XCMG:
    each has authoritative `VERIFIED_RESTRICTED` legal evidence that ADR-0005
    maps to `PAUSE`, so a private-use scope cannot rewrite it to `ADMIT`. The
    sole replacement is the existing `ENT-009` `sany-construction-cases`
    research stream. Its official list, fixed detail `/case/16504.html`,
    robots, and legal-statement pages currently return HTTPS `200`; the existing
    machine record marks robots, terms, and copyright evidence `VERIFIED`, and
    the legal statement permits personal noncommercial use while prohibiting
    public full-text/media redistribution. The acceptance profile now fixes new
    SourceStream ID `019fb870-06f4-7227-a03e-a6b11dcbf91e`, discovers only the
    same fixed document through the real list parser, and labels its evidence as
    manufacturer claims. No model call, database acceptance run, publication,
    formal-database write, or Phase 5 work occurred while preparing this repair.
    It remains `NO_GO` until the repair SHA passes `check-fast`, full `check-pr`,
    one `check-release`, same-SHA remote CI, and the complete isolated live chain.

29. Replacement-source candidate `73b631cce156894f1b44daf06cd1a37ad0d525b5`
    passed `check-fast`, full local `check-pr`, its one exact-SHA
    `check-release`, and same-SHA GitHub Actions run `30637221408`. Live project
    `srbg-phase4-60425e4e01bd` stopped before source access because Compose read
    the normal stack's `.env` value `MINIO_CONSOLE_PORT=29001`, already owned by
    `srbg-issue40-minio-1`; the acceptance runner had randomized PostgreSQL,
    Redis, MinIO API, and anchor MinIO ports but not the MinIO console port. It
    made no source or model request, generated no document or publication, and
    incurred zero model cost. Teardown removed all three containers, all four
    project-scoped volumes, and the project network. A focused regression was
    red before the minimal repair and now requires a separately allocated
    `MINIO_CONSOLE_PORT`. The repair does not stop or reconfigure the existing
    MinIO, Docker stack, VPN, source, model, budget, formal database, or
    publication path. Phase 4 remains `NO_GO`; Phase 5 remains unstarted.

30. MinIO-console repair candidate `23df096d88fc60085beed0f84bbeb89e596abc76`
    passed `check-fast`, but its complete `check-pr` attempts exposed only
    external gate failures: first PyPI closed one TLS connection during
    `pip-audit`; the next run passed dependency audit but Trivy reported
    `cannot allocate memory` and BuildKit returned RPC `EOF`; after the
    previously authorized Docker Desktop restart, Trivy again failed with the
    same allocation error. Code, migration, contract, and unit assertions were
    green before each stop. Docker Desktop had 15.44 GiB shared by multiple
    active user projects; stopping those projects was not authorized. Trivy
    documents `--parallel` with default 5, so the minimal repair fixes its
    scanning concurrency at 1 while preserving the same Git-delivery input,
    `secret,misconfig` scanners, HIGH/CRITICAL severity, and exit-on-finding
    behavior. A focused regression was red before the change. The full security
    target then scanned 1,311 files and passed with zero findings without
    stopping another project. No source/model request, document, publication,
    model cost, formal-database write, or Phase 5 work occurred. Phase 4 remains
    `NO_GO` pending the new repair SHA's complete gates, same-SHA CI, and live
    rerun of the unchanged fixed document.

## Trusted DNS repair authorization (append-only)

20. The Owner authorized an application-scoped repair after confirming it
    will not modify FlClash, Windows DNS, adapters, proxy, routes, firewall,
    hosts, other software, or other projects. Diagnosis proved the system
    resolver returned changing `28.0.0.x` synthetic addresses while the
    FlClash Meta Tunnel owned the default route. The repair adds an
    authenticated RFC 8484 resolver with a fixed public bootstrap address,
    makes its endpoint a single platform-level setting, and injects it into
    source runtime, personal probes, discovery probes, and the existing pinned
    paid-search transport. DoH failure does not fall back to system DNS; the
    existing public-IP, DNS-rebinding, redirect, response-size, deadline, and
    connected-peer checks remain unchanged. Resolver and runtime tests were
    red before implementation and the focused suite now passes. No source
    page or model request was made while implementing this repair. Phase 4
    remains `NO_GO` until the new SHA completes every repair gate, same-SHA CI,
    and the complete isolated real-content chain.

21. The first bounded DoH integration check failed closed before source HTTP
    because available `dnspython 2.8.0` attempted an unavailable HTTP/3 path
    and then expected the separate `httpx` package. The repair did not add a
    second HTTP client: dnspython now only creates and validates RFC 8484 DNS
    wire messages, while the repository's existing `httpx2` pinned transport
    performs authenticated HTTPS to the fixed public bootstrap address with a
    bounded response and peer check. A regression test was red before this
    change. The next DNS-only check resolved `www.ccccltd.cn` to real public
    addresses `27.155.113.133` and `240e:95c:806:40::403`, rather than the
    FlClash synthetic `28.0.0.x` range. No source HTTP or model request was
    made by either DNS check.

22. Repair candidate `b3392699dc47692db69a6b9f78f2c3edbcbdbcbd`
    passed `check-fast`, full local `check-pr`, and its one exact-SHA
    `check-release`, but same-SHA GitHub Actions run `30628202345` failed on a
    fresh PostgreSQL cluster before any live acceptance request. Migration
    `0016_scheduling_health_replay` granted `retention_execution` directly to
    deployment login `srbg_publisher_login`, which was absent in that fresh
    cluster even though the migration-owned `srbg_publication_writer` role
    existed. A regression test reproduced the direct-login dependency before
    the minimal repair changed that grant to `srbg_publication_writer`.
    Disposable publisher logins inherit that same role, so no ACL capability,
    publication gate, source rule, budget, or formal database was widened or
    changed. Phase 4 remains `NO_GO` pending the repaired SHA's complete local
    gates, one release gate, same-SHA remote CI, and full isolated live chain.

23. Repair candidate `345b6e4fad7aae360fe0566bfe3eda99546a4fbd`
    passed `check-fast`, full local `check-pr`, its one exact-SHA
    `check-release`, and same-SHA GitHub Actions run `30629105327`. Live
    profile `srbg-phase4-b700daaf3a3a` used the independent authenticated DoH
    path successfully, then its one bounded direct request to the fixed CCCC
    list URL still received HTTP `521`. It stopped before discovery, raw
    persistence, document selection, or model use. Evidence file
    `.cache/phase4-evidence/345b6e4fad7aae360fe0566bfe3eda99546a4fbd-b700daaf3a3a.json`
    records SourceStream `019fb785-8785-70d5-921c-10c8bc029549`, zero model
    calls and cost, and a successful drain with zero database tasks and Redis
    keys; teardown removed all scoped containers, volumes, and network. This
    remains `NO_GO`.

24. The next repair is application-scoped and does not edit FlClash, Windows
    DNS, system proxy, routes, firewall, hosts, or other projects. An explicit
    optional local SOCKS5 route tunnels only an independently resolved,
    SSRF-approved public target IP; the proxy never resolves the source
    hostname, and TLS still authenticates the original hostname. The setting
    accepts only loopback or the Docker host gateway, forbids credentials, is
    disabled by default, and does not inherit system proxy state. Protocol,
    pinning, configuration, and production-composition tests were red before
    implementation and pass after the minimal repair. No source or model
    request was made while implementing it. Phase 4 remains `NO_GO` until a
    repaired SHA passes every required gate, same-SHA CI, and the complete
    isolated live chain.

25. Repair candidate `15ea564aa1764a7436697e178ea63486f34d69a5`
    passed `check-fast`, full local `check-pr`, its one exact-SHA
    `check-release`, and same-SHA GitHub Actions run `30630659102`. Live
    profile `srbg-phase4-30e9513ec6d9` enabled the optional route only through
    its process environment. Independent DoH resolution succeeded, but the
    source transport failed before an HTTP response, discovery, raw-object
    persistence, document selection, or model use. Evidence file
    `.cache/phase4-evidence/15ea564aa1764a7436697e178ea63486f34d69a5-30e9513ec6d9.json`
    records the fixed SourceStream, `0` model calls, `0` cost, and a successful
    drain with zero database tasks and Redis keys; teardown removed all scoped
    containers, volumes, and the network. The live harness had omitted the
    production runtime's existing request/response accounting callbacks, so
    failure settlement rejected the transport's request count and masked the
    original bounded transport classification. A focused regression was red
    before the minimal repair. The harness now reserves each physical request
    in the authoritative schedule, records response bytes, and appends the
    persisted bounded `fetch_run.failure_class` to failure evidence. It does
    not change proxy behavior, SourceAdmission, robots, terms, rate, budget,
    publication, FlClash, Windows networking, other software, or other
    projects. No source or model request was made while implementing this
    repair. Phase 4 remains `NO_GO` pending the repaired SHA's complete gates,
    same-SHA CI, and full isolated live chain; Phase 5 remains unstarted.

26. Repair candidate `5f4446ec704ea7286182b1b250d5bca8f9116ff0`
    passed `check-fast`, full local `check-pr`, its one exact-SHA
    `check-release`, and same-SHA GitHub Actions run `30632033996`. Live
    profile `srbg-phase4-474bdfb25a58` used the process-scoped SOCKS route;
    both independent DoH queries succeeded and the fixed CCCC list URL
    returned HTTP `521`. Append-only evidence file
    `.cache/phase4-evidence/5f4446ec704ea7286182b1b250d5bca8f9116ff0-474bdfb25a58.json`
    records one authoritative request, bounded failure class `HTTP_5XX`, no
    discovery or document, `0` model calls, and `0` cost. It also records
    `active_database_tasks=1`, `redis_keys=0`, and `drained=false`: the 5xx
    result was correctly placed in `RETRY_WAIT`, but the acceptance stop path
    paused its schedule without cancelling that now-ineligible run. Although
    runner teardown subsequently removed every scoped container, all four
    named volumes, and the network, physical deletion does not rewrite the
    failed database-level drain result. The next minimal repair calls the
    existing scheduling authority to cancel only the exact unleased fetch run
    after Owner intent, schedule, and source authority have been closed, then
    counts remaining work. Its focused regression was red before the repair
    and now passes. It does not change HTTP classification, retry policy,
    source access, proxy behavior, budget, AI, publication, FlClash, Windows
    networking, other software, or other projects. No new source or model
    request was made while implementing the repair. Phase 4 remains `NO_GO`;
    the formal database stage is not authorized and Phase 5 remains unstarted.

27. Drain-repair candidate `07ddd8e3c41ceb49b244c01635d3e7533efe8c64`
    passed `check-fast`, full local `check-pr`, its one exact-SHA
    `check-release`, and same-SHA GitHub Actions run `30634645687`. Two local
    `check-pr` attempts had first stopped at `web-a11y` when Docker Desktop's
    Linux Engine and `docker-desktop` WSL control channel returned HTTP `500`
    and `Wsl/Service/0x8007274c`; after the previously authorized Docker
    Desktop restart, the same clean SHA passed the complete gate. No FlClash,
    system-network, VHD layout, or repository change was used to clear it.
    Live profile `srbg-phase4-819a891c0d5c` then used the same fixed
    SourceStream, independent DoH, application-scoped SOCKS route, budget,
    model, deadline, and retry limits. Its one authoritative list request again
    returned HTTP `521`. Append-only evidence file
    `.cache/phase4-evidence/07ddd8e3c41ceb49b244c01635d3e7533efe8c64-819a891c0d5c.json`
    records bounded failure class `HTTP_5XX`, no discovery, no Document, `0`
    model calls, and `0` cost. The repair is proven: stop/drain records
    `active_database_tasks=0`, `redis_keys=0`, and `drained=true`; teardown
    removed every scoped container, all four named volumes, and the network.
    The fixed official endpoint has now returned the same `521` through both
    pinned direct and application-scoped VPN paths. No eligible document was
    selected, so raw object through Reader and replay could not run. Changing
    to HTTP, proxy-side DNS, an unresearched mirror, a second source, or another
    unapproved egress would weaken or expand the frozen authorization and was
    not attempted. This is an honest `NO_GO`: the formal database stage is not
    authorized and Phase 5 remains unstarted.

### Final resumed acceptance state

- RELEASE_CANDIDATE_SHA: `07ddd8e3c41ceb49b244c01635d3e7533efe8c64`
- SourceStream ID: `019fb785-8785-70d5-921c-10c8bc029549`
- Document ID: not generated; the fixed list endpoint returned HTTP `521`
- Model calls and cost: `0`; `0` micro-USD / RMB `0`
- Full chain: stopped at the authoritative list fetch with `HTTP_5XX`; raw
  object through Event Reader did not run
- Feed/Reader: not generated / not run
- Replay: not run because no document, Event, or publication existed
- Queue/resource drain: `PASS` (`0` active database tasks, `0` Redis keys,
  and no scoped Docker container, volume, or network)
- Decision: `NO_GO`
- Formal database stage: `NOT AUTHORIZED`; Phase 5 remains unstarted
