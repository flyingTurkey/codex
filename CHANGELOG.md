# Changelog

## 2026-07-31 (Phase 4 controlled real Event acceptance — resumed)

- Preserved the original Phase 4 `NO_GO` record unchanged and resumed only after the Owner restated that `NO_GO` cannot unlock Phase 5.
- Repaired the isolated data-root readiness boundary so Prometheus and Grafana permissions are applied to the configured `SRBG_DATA_ROOT`, not an unrelated default path; the frozen repair candidate passed local `check-fast`, `check-pr`, and exact-SHA `check-release`.
- Reproduced the fresh-runner CI failure where migration `0016` grants to `srbg_publisher_login` before that role exists. The autonomous migration gate now waits for the existing Compose `role-bootstrap` service before creating its disposable database; no migration, ACL, publication rule, or production database was changed.
- Made repeated Windows runtime readiness distinguish an already attached system VHD from a not-yet-visible Docker Desktop mount, wait up to ten seconds for bounded propagation, and fail closed instead of trying to attach the same VHD twice.
- Replaced the Phase 4 runner's Windows/NTFS bind-backed disposable databases with project-scoped PostgreSQL, WAL, Redis, and MinIO named volumes after the first live profile stopped before source access because PostgreSQL could not set `initdb` permissions. The override is acceptance-only and `down --volumes` removes every ephemeral volume.
- After candidate `444a31b2d6a30ae7e2a1cde322d9f18dc7583ff3` passed local gates and same-SHA CI, its live profile reached the fresh migration and stopped at the first confirmed blocker: the Phase 4 runner had not invoked the existing role bootstrap before migration `0016`. The runner now executes that bootstrap before the verifier; no migration or grant rule is weakened.
- The next same-SHA-approved live profile stopped before network access when its acceptance seed put a host-plus-path value into the host-only `authorization_boundary`. The bounded repair keeps the hostname in that existing field and retains the already governed path prefix in `personal_controlled_run_source.path_prefix`; it does not widen the accepted source path.
- No real source or model request has been made during this resumed attempt. The repaired SHA must pass the complete repair gates, same-SHA remote CI, and the isolated live acceptance before any `PASS`; Phase 5 remains unstarted.

## 2026-07-30 (Phase 4 controlled real Event acceptance — NO_GO)

- Added a guarded, one-document `phase4-real-event` live profile for a researched `cccc-project-briefs` SourceStream, fresh isolated PostgreSQL/Redis/MinIO resources, fixed DeepSeek model settings, an 80,000-micro-USD fail-closed cap, a 25-minute wall deadline, replay checks, and append-only evidence output. Ordinary pytest partitions collect but never execute the live profile.
- Closed the pre-live publication-date gap by allowing `intelligence_item.source_published_at` to be projected only from an automatically accepted, directly evidenced `published_at` claim; invalid, future, and conflicting dates fail closed.
- Made Playwright browser gates declare their pinned Chromium runtime dependency after the first release attempt proved a fresh worktree could otherwise fail before any browser assertion.
- Recorded `NO_GO` before any real source or model call: the second frozen candidate passed `check-fast` and `check-pr`, but its only `check-release` attempt timed out in `compose-smoke` while Docker Compose waited for the full runtime. The release process tree was stopped, but Docker Engine HTTP 500/timeout prevented proof of container and queue drain. Nothing was pushed, no remote CI ran, no formal database was written, and Phase 5 was not started.

## 2026-07-30 (Phase 3 minimal trustworthy Event slice)

- Closed the Phase 2 proven gap between accepted AI content and Reader visibility: the real Worker now continues from `SUMMARIZE` through deterministic `VERIFY`, and atomically persists the verified step, accepted SourceExcerpt, approved-content success, terminal handoff, and projection outbox. A billable provider response is still settled and recorded when callback validation fails.
- Added stable evidence-anchor rejection codes and kept claim/evidence bidirectional validation at the same callback boundary used by a real provider. The deterministic acceptance adapter uses the production Prompt, JSON Schema, Pydantic, evidence locator, failure classification, token, and cost interfaces without public-network or real-model access.
- Added linear migration `0055_phase3_trustworthy_event` from `0054_policy_optimization`. Automatic publication is bound to current VERIFY authority, accepted-claim hash, current SourceStream definition/config hash, authority epoch, and Owner veto; Publisher and Worker receive only the narrow locking/loading commands required by their existing responsibilities.
- Made `PublicationService` the sole automatic FULL publication path and committed publication revision, Reader projection, search projection, suppression matches, and publication decision in one Publisher transaction. Reader visibility now revalidates the exact current revision and authority epoch; stale projection writes cannot move visibility time backwards.
- Added a disposable PostgreSQL/Redis/private-MinIO vertical acceptance that enters through the real SourceAdapter and raw-first flow, reaches `/api/v2/feed` and Event Reader, proves replay idempotency, R3/R4 non-leakage, machine-organized status, Owner veto/restore, and `0054 -> 0055 -> 0054 -> 0055` data/ACL replay.
- Extended the risk classifier so migration, AI, content, publication, and integration changes automatically select `phase3-trustworthy-event-test`; no stop/drain plane, governed replay UI, dashboard, advanced Feed filtering, campaign ledger, multi-source expansion, or live connectivity was added.
- Corrected the Web image's pnpm cache mount to the store path actually used inside `/workspace`, made that store path explicit, and used pnpm's reviewed-lockfile mode so cached rebuilds do not repeat registry-wide supply-chain metadata verification. Contract tests cover the frozen lockfile and cache-path boundary; the independent dependency security gate remains unchanged.

## 2026-07-29 (Phase 1 authority cleanup)

- Reframed `AGENTS.md` around durable product, architecture, evidence, publication, security and UI boundaries. Behavior changes remain test-first, while documentation and mechanical work use proportionate checks; validation now follows path risk and exact-SHA evidence instead of unconditional full-suite reruns.
- Rebuilt the root README as an Owner-facing capability and startup guide. It distinguishes registration, research, runtime authorization, Worker activity, raw/document persistence, AI completion, accepted claims/evidence, PublicationService output, v2 Feed visibility and human review.
- Corrected active user, maintenance, architecture and recovery guidance to the `0054_policy_optimization` baseline. Historical `0033`/`0045`/`0047`, Txx/PERS and Owner Gold evidence remains in its original history and acceptance records rather than being presented as current runtime state.
- Recorded the remaining proof gap explicitly: this baseline has not yet demonstrated one real external source flowing through raw/document, AI, accepted claims/evidence and `PublicationService` into v2 Feed. No production data, source authorization, real AI configuration or Compose semantics changed.

## 2026-07-29 (Docker dev-lite and formal 0054 migration)

- Added a resource-conscious `make dev-lite` runtime: core services plus the automation plane remain available while discovery, AI, and observability are opt-in profiles. The default steady state is 12 long-lived containers instead of 18; Celery defaults to one task slot, health probes run less often after startup, runtime logs rotate, and Prometheus has both time and size retention limits.
- Prevented one-shot PostgreSQL role tasks and Alertmanager from allocating anonymous image-declared volumes. Role tasks cover PGDATA with tmpfs; Alertmanager uses a writable uid/gid-scoped tmpfs. Full-to-lite replay holds the Docker volume count at 188 with zero project anonymous mounts.
- Integrated the green `codex/issue-40-integration` candidate and formally migrated the Owner's local PostgreSQL from `0047_owner_gold_override_go` through all seven revisions to `0054_policy_optimization`. The migration ran only after a byte-identical, read-only-mounted VHD snapshot and an independent logical restore passed; critical business counts were unchanged and expected ACL/schema checks passed.
- Restored the formal runtime in dev-lite, validated the full 23-entry / 18-long-lived profile, and returned Docker Desktop to the 17-entry / 12-long-lived light state. API live/ready, v2 Feed, Web SSR/proxy, Smoke, dependency audits, Trivy, lint, strict type checks, unit/integration tests, and contract generation gates pass.
- Recorded the pre-0054 artifact hashes, the initial fail-closed logical restore caused by missing RLS roles, the safely cleaned local-port conflict, the Alertmanager tmpfs permission correction, and the VHD-first rollback boundary in the Docker and formal-migration acceptance records. This is a local formal-database migration and runtime closeout, not an external production deployment or production authorization.

## 2026-07-29 (Issue #40 isolated migration ACL rollback hardening)

- Fixed downgrade grant symmetry in migrations `0049`, `0052`, and `0054`: Worker candidate-table access, Publisher Feed-suppression writes, and API/Worker policy-projection reads are now revoked at the revision that introduced them while older baseline grants remain intact.
- Extended the real PostgreSQL migration verifier with direct `public` table/view ACL snapshots at `0048`, `0051`, `0053`, and the complete `0047 -> 0054 -> 0047 -> 0054` cycle. The three regressions were reproduced before implementation and are covered by focused migration tests.
- Repeated the candidate chain against a read-only physical clone of the formal PostgreSQL data. Stepwise downgrades and the complete rollback restored the `0047` schema, data, and direct table ACL fingerprints exactly; re-upgrade to `0054` also passed. Formal PGDATA, WAL, and `alembic_version` were not changed.
- Cleared newly published production dependency advisories by resolving `brace-expansion` to `5.0.8`, `postcss` to `8.5.18`, and `tar` to `7.5.21`; the frozen install, full test suite, production audit, and HIGH/CRITICAL security gate pass.
- Fixed a latent technical-exception recovery defect exposed by the candidate branch's fresh CI run: repeated Owner recovery now follows the unique `source_content_outbox.pipeline_run_id` binding instead of guessing from historical pipeline timestamps, and projects only a `DEAD_LETTER` / `FAILED` technical run. The integration seam deliberately keeps its retry clock behind the handoff wall clock and verifies that re-exhaustion rebinds the existing exception to the actual failed recovery pipeline.
- The migration/ACL result is an isolated candidate-fix `PASS`; the technical-recovery follow-up is accepted only through the candidate branch's full remote CI. Neither result is a formal-database migration or production closeout. The Owner authorized local commit, fast-forward integration, repair/retest, and remote candidate push on 2026-07-29; formal-database migration remains a separate action.

## 2026-07-23 (Issue #46 Champion/Challenger policy optimization)

- Bound every newly created LIVE and SHADOW AI pipeline run to an immutable policy bundle so callbacks, physical retries, semantic rechecks and technical recovery cannot change policy mid-run; later activation affects only later runs.
- Added append-only offline evaluation, aggregate shadow-window, activation and live-health facts. A derived active pointer supports exact-baseline bootstrap, gated Challenger promotion and idempotent rollback without modifying historical bundles, decisions, evaluations or shadow facts.
- Kept replay evaluations structurally `authorizes_production=false` and shadow decisions `affects_production=false`. Offline success grants only shadow eligibility, and shadow work terminates before Item, claim, Event, PublicationService or Feed materialization.
- Added automatic Challenger selection, aggregate Champion comparison, hard promotion gates and production-health rollback across Feed yield, filtering, technical exceptions, Safety holds, suppression/restoration, Schema/projection failures, hard-negative leakage, budget and category drift.
- Extended the single governed SourceStream-to-Feed integration seam to prove policy freezing, promotion and rollback with zero Owner semantic-classification tasks. Added migration replay, low-cardinality observability, alerts, ADR-0006, maintenance/context documentation and an honest acceptance split between mechanism completion, real Challenger promotion and production closeout.
- Preserved the historical `.4` result at 70% precision, 70% recall and five locked-negative leaks: it remains `NO-GO`; no threshold or historical fact was rewritten.

## 2026-07-23 (Issue #45 Safety holds and Owner decisions)

- Unified deterministic prompt-injection pre-scan findings and AI `security_signals` into the existing `owner_exception_v2` Safety lifecycle. The server maps the frozen closed reason set to `OWNER_DECIDABLE` or fail-closed `HARD_BLOCK`; `SAFETY_INTELLIGENCE` remains an ordinary primary content type.
- Kept Safety authority orthogonal to qualification: pre-scan holds continue through the normal classifier, while AI-signal candidates must pass every non-safety relevance, axis, and evidence rule before any publication context is materialized. Invalid candidates remain held but cannot acquire a qualification acceptance; their server-normalized Safety reason is preserved independently.
- Extended the existing `/api/v2/owner/exceptions` list, detail, and optimistic/idempotent command surface without a second router, exception ledger, or semantic review queue. Safety projections expose only bounded substitute metadata and safe evidence references, never dangerous content, attachments, media, or raw model output.
- Added linear migration `0053_safety_exception_lifecycle`. Its security-definer writer creates one append-only Safety exception/event/audit trail per durable `SAFETY_HOLD`, while the shared security-barrier projection excludes every open hold from Feed, search, hotspots, Event detail, appendix, and media authorization.
- Made Owner allow/deny decisions append-only and concurrency-safe. Allow applies only to `OWNER_DECIDABLE` and calls `PublicationService` for current authoritative re-evaluation before automatic Feed visibility; deny reuses the #44 suppression service to create the sole `SAFETY_DENIAL` terminal rule. Neither path writes publication status directly or asks for a second confirmation.
- Serialized the complete Owner Safety command around its external publication effect and made a durable `PENDING` action resumable, so same-key races and process interruption converge on one truthful final result instead of returning provisional success.
- Kept private-network, loopback, cloud-metadata, malicious-payload, access-control-bypass, mandatory-malware-scan, missing-safe-bytes, and unknown security signals non-overridable. A hard-block allow command returns deterministic Problem Details and cannot create a projection.
- Expanded the same accessible Nuxt Owner exception workspace with a Safety partition, safe reason labels, explicit hard-block state, one-click allow/deny, keyboard/zoom/axe coverage, low-cardinality backlog/command metrics, migration replay, and the existing highest SourceStream-to-Feed acceptance seam.

## 2026-07-23 (Issue #44 Feed suppression and automatic restoration)

- Activated the frozen `feed_suppression_rule_v2` contract as an append-only, idempotent, audited Owner control plane under `/api/v2/owner/suppressions`, with canonical scope targets, serialized concurrent commands, explicit revoke preconditions, and no Safety allow/deny or technical-retry authority.
- Added linear migration `0052_feed_suppression_projection` from the actual `0051` head. Its rebuildable Event match model covers Event, primary type, engineering object, specialty, equipment, Source, and custom-topic keys; existing projections are backfilled without changing historical migrations or creating another suppression ledger.
- Routed Feed, search, hotspot, Event detail, appendix, preview, and download authorization through one PostgreSQL security-barrier visible projection before ranking, pagination, cursor, counts, or `LIMIT`. Suppression never deletes source material, evidence, claims, decisions, or historical facts.
- Kept `AUTO_ACCEPTED` content entering Feed through the existing `PublicationService`. Revocation appends a fact and re-evaluates each affected current document through that same gate; successful current content restores automatically, while current gate failures remain closed without requiring Owner confirmation.
- Added the shared Feed-card confirmation action and an accessible Nuxt Owner control page for creating and revoking rules, plus a v2 same-origin proxy, bounded metrics, migration replay, SQL-boundary tests, browser/axe coverage, and the existing unique SourceStream-to-Feed acceptance seam.
- Added the same accessible hide action to the unified Event Reader, complete Event-wide SOURCE and confirmed custom-topic matching with shared Unicode canonicalization, failure-safe revalidation-before-REVOKE ordering, and a bounded failure alert/runbook.
- Hardened revocation convergence with same-key replay before rebuild work, winner-timestamp convergence for losing writers, explicit HTTP 412 conflict feedback, legacy-safe oversized custom-topic handling, and acceptance coverage for a rule predating the real raw/document handoff plus object-storage media suppression/restoration.
- Serialized each Event projection write and made its timestamp monotonic, so an older reconstruction cannot overwrite a newer visibility decision. The production SourceStream seam now exercises all seven frozen scopes across Feed, search, hotspot, and Event reads, including a controlled losing-writer interleaving.

## 2026-07-22 (Issue #43 technical exception control plane)

- Added retryable/non-retryable autonomous technical failure decisions with three PostgreSQL-backed exponential retry intervals, full jitter, leased restart recovery, terminal `TECHNICAL_FAILED`, and a separate retry-cycle counter so Owner recovery never reuses an immutable decision attempt number.
- Added the local Owner `/api/v2/owner/exceptions` list/detail/command surface, idempotent immediate-retry requests, automatic resolution after a later accepted/filtered decision, tamper-evident command audit, bounded metrics, and an exhaustion alert. Existing source intent PATCH remains the sole one-click source-disable authority.
- Added the Nuxt technical-exception workspace with status filtering, retry/disable controls, duplicate-click protection, Shanghai time display, responsive token-driven styling, and browser/axe coverage.
- Extended the safe Owner projection with a nullable bounded technical reason, kept Safety projections null, and added linear migration `0051_technical_exception_recovery`. Its event-bound `SECURITY DEFINER` commands resume failed AI or SourceStream work without granting direct shared-table writes or creating a parallel Alembic head.
- Reused the existing durable SourceStream scheduler for acquisition failures and extended the same technical path across raw-object loading, deterministic parsing/evidence failures, queue dispatch, temporary database/object-store outages, and stale-run restart recovery. This change does not add Safety Hold adjudication, Owner allow/deny actions, Feed suppression, or publication authority.

## 2026-07-22 (Issue #41 autonomous production closeout)

- Switched the real content Worker to the versioned autonomous rule/AI adjudication seam. Deterministic negatives stop before Item/Event creation; accepted candidates retain exact policy/model/Prompt/Schema/document identities and continue only through evidence qualification and `PublicationService`.
- Removed HUMAN_OWNER Gold from production SourceAdmission. Explicit network/access/legal prohibitions still pause, while missing legal metadata and soft-quality observations allow bounded collection. `OWNER_OVERRIDE_GO` grants no authority.
- Preserved SourceStream bridge runs as `LIVE` through autonomous preparation, while `SHADOW` decisions remain non-projecting. Classification leakage is now a policy-iteration signal rather than a source-collection veto, and migration 0049 verifies that the immutable Prompt registry hashes match the exact shared production/replay templates.
- Connected the production admission verdict to the authoritative assessment writer and closeout verifier, re-authorized LIVE callbacks across nonterminal states, and persisted SHADOW results only in `affects_production=false` tables. The accepted integration now enters through a governed raw capture, WAITING_AI handoff and real Worker authorization entry.
- Preserved `INDUSTRY_UPDATE` as a distinct Item/channel/Event compatibility type and v2 Feed category. The durable publisher outbox now has an isolated accepted-path integration proving evidence-backed FULL machine-organized projection without an Owner semantic case.
- Added migrations `0049_autonomous_content_switch` and `0050_autonomous_handoff_state_order`, ADR-0005, retry-attempt convergence after Schema repair plus semantic recheck, and migration/filtered/accepted production integration coverage while preserving 0046/0047.
- Fixed GNU Make default/export ordering so clean environments receive bounded service ports, local database/object-storage credentials, buckets, regions, and external-I/O timeout instead of invalid empty values, with a regression test covering the full environment contract.
- Gave the CI integration job its own ephemeral `SRBG_DATA_ROOT`, pre-created with least-privilege service ownership, preserving the mandatory PostgreSQL, Redis, object-storage, and observability data isolation contract on clean runners.
- Added an idempotent login-role bootstrap before Alembic on clean databases, so historical grants can migrate forward before the existing post-migration role/password initialization; historical revisions remain unchanged.
- Whitelisted only the #41 autonomous classification Schema into the runtime image build context so migration 0049 can register and hash the same authoritative bytes on clean deployments.
- Replaced the stale CI target for the retired enterprise Safety Case lifecycle with an explicit #41 autonomous-content integration gate covering real isolated database, Worker/evidence, and PublicationService paths for safety and industry Feed projections; Round 04 immutable fixtures remain in offline replay.
- Extended that integration gate through the actual personal SourceStream scheduler, bounded network and malware-scanner edge replacements, and private MinIO raw-first persistence while keeping production ClamAV private-network-only. Migration `0050_autonomous_handoff_state_order` removes a random UUID tie-break from same-timestamp document lifecycle states, and the gate now proves deterministic handoff to filtering or publication.
- Preserved the one-recheck bound across every Worker redispatch, mapped unknown robots/terms/copyright observations to bounded admission instead of a false prohibition, and centralized production admission assessment writes in the shared SourceAdmission service.

## 2026-07-21 (Issue #41 autonomous qualification policy foundation)

- Added immutable, version-bound qualification policy and automated disposition contracts beside the preserved 0046/0047 Owner Gold history. Migration 0048 adds append-only decision, exception-event, suppression, offline/shadow evaluation, and shadow-decision foundations without granting `OWNER_OVERRIDE_GO` any new authority.
- Added deterministic engineering/safety/domain rules, a strict autonomous classification Schema and Prompt, one bounded semantic re-adjudication, safety holds, and aggregate-only private replay plumbing. Confidence remains diagnostic and all offline/shadow facts are structurally non-production-authorizing.
- Authenticated the private corpus, sealed predictions, Owner attempt and annotations as a single hash chain, rejected duplicate case/annotation/response identifiers, and kept live candidates and decision traces process-local. Added broader lifecycle-bound construction-machinery vocabulary and a bilingual bounded-recheck checklist. The reviewed 40-case aggregate remained `NO-GO`, so no production path was authorized.
- Added ADR-0004 and shared T03-T06 exception, Feed suppression, evaluation, shadow and reason-code contracts. Worker, SourceAdmission and PublicationService production paths remain unchanged; no source, production traffic or later ticket was enabled.
- Hardened the private live replay transport with a pinned tool-free DeepSeek profile, one bounded transient retry, process-local candidates, and at most two offline workers. Reconciled the inherited closeout fixture and validator with the frozen 20-positive/20-negative Owner Gold contract; quality thresholds remain unchanged.
- Evaluated stronger model and adjudication topologies under expanded Owner authority. None exceeded the held-out gate, so all quality-regressing semantic experiments were removed and the best reviewed aggregate remains `NO-GO`; no benchmark-specific exception or production authorization was introduced.
- Closed code-review gaps by making safety signals from the single bounded re-adjudication enter `SAFETY_HOLD`, binding the policy digest to the actual Prompt and output Schema bytes, and rejecting oversized private replay artifacts before parsing or hashing. The frozen quality threshold and production-path boundary remain unchanged.
- Made retry convergence append-only and idempotent by keying immutable automated decisions by document, policy, and bounded attempt number. Private model calls now retain process-local hash-only invocation audits with latency, token usage, and provider cost when supplied; manifest, key, artifact, and provider-response reads are size-bounded before parsing or hashing.

## 2026-07-20（土木工程情报 v2 维护信息收口）

- 新增单一维护入口，汇总已验证工程基线、当前 dirty worktree、本地数据库状态、#36→#35 剩余依赖链、现行 production 门槛、下一轮安全顺序和文档债务；历史验收记录继续作为点时证据保留。
- 只读复核确认 `.4` 已有 40 条 Owner 标注，但标准校准为 `NO_GO`：实际分布 20/0/20、precision 55.55%、recall 75%、锁定负例泄漏 9；#36 仍 OPEN，#14 仍被阻塞。
- 标记未批准的 0047 override 冲突：本地 PostgreSQL 已应用对应 migration 并持久化 `authorizes_auto_pass=true` 的事实，但它同时记录质量门槛未满足，不得合入基线或作为 SourceAdmission、PublicationService、closeout 和关票证据。本轮未删除、降级或重写该追加式事实。
- README 与总体验收记录增加当前状态入口并同步 Spec #1 的每源 1.5 小时、首十 24 小时、DeepSeek 2 小时/2 次和 Feed Owner 50 条口径；保留 AI 24 小时新鲜度、200 条工程结构审计及两个 14 天退出窗口。ADR-0003 收敛为 profile 语义隔离和失败关闭决定，不再充当可变数字配置源。
- 将 `docs/codex-kit/AGENTS.md` 收敛为 Legacy 作用域护栏，阻止旧企业/OIDC/v1 规则在子目录继续覆盖根规则；为 codex-kit README、根 `README-1.md` 和根 `VALIDATION.md` 增加历史状态与现行入口指针，未删除历史材料。
- 本轮仅整理文档和只读核验，没有修改业务代码、启用来源、执行发布、关闭 issue、删除历史文件或提交私有 Owner Gold 行级材料。

## 2026-07-20（Issue #36 Owner Gold 40 条盲标准备）

- 将生产 Owner Gold 契约从旧 360 条同步为冻结 40 条：20 正例、10 边界例、10 锁定负例，正例三主类型 7/7/6；旧 360 条仅保留为 `STRUCTURAL_REPLAY`，不能签发生产授予。
- 新增 `0046_owner_gold_prediction_seal`、服务端重算哈希的追加式 seal/fact 写入、私有冻结/预测/封存/盲标/校准 CLI，以及 qualification、SourceAdmission、PublicationService、production closeout 的精确 corpus/rule/model/prompt 与 seal/fact hash 失败关闭消费；工程 closeout 行为保持不变。
- `owner-gold-2026-07-20.1` 的 40 条 Owner 尝试以 `15/3/22`、正例主类型 `7/8/0`、对象覆盖 `9/11` 且专项/设备缺失的确定性 `NO_GO` 私有封存；15 条已知正例仅形成 `production_calibration_eligible=false` 的培训回放，未生成生产 `owner-gold.jsonl` 或校准事实。
- 私有 `owner-gold-2026-07-20.2` 从 80 条全新公开候选确定性冻结并完成预测封存后，在标注前设计复核中发现 1 条铁路安全材料被错误预注册为数字化正例；未查看预测或 Owner 标签，整版以 `PREREGISTERED_POSITIVE_CENTRAL_FACT_MISMATCH` 确定性 `NO_GO` 保留，禁止原地替换。
- `.3` 重新生成全部 case ID 并完成 40/40 冻结与预测后，标注前正文复核发现三个预注册工程对象没有正文证据；未读取预测或 Owner 标签，整版以 `PREREGISTERED_ENGINEERING_OBJECT_NOT_EVIDENCED` 确定性 `NO_GO` 保留，禁止原地修补。
- 通过带 base hash 的显式 amendment 递增为 `owner-gold-2026-07-20.4`，新增正文对象/主类型/专项/设备硬门禁并重新生成全部 case ID；首次 freeze 失败的 38 个原始对象和原因另存 NO_GO attempt，随后在 seal 前修正预注册对象元数据并成功冻结 40 条。`.4` 和 `.1` 的 case、URL、内容哈希交集均为 0，设计覆盖 20/10/10、7/7/6、十一对象、两条施工机械和一条交通隧道瓦斯组合。
- `.4` 的 40 条独立 DeepSeek 预测已在任何 Owner 草稿产生前执行并追加封存，prediction seal 为 `038145f4f1cd841a41dc4c5e8827c62b3a995bac68b785805f9bf7776f702da7`，blind pack 字段泄漏检查通过；正文、预测和标注均未进入 Git，生产消费者只接受 `.4`。
- 当前停在 `.4` Owner 逐条盲标入口：未创建 HUMAN_OWNER 标注、未生成最终校准 GO、未关闭 #36、未启动 #14、SourceStream 或真实来源观察波次，也未修改 AI 运行、DeepSeek、Feed 抽检、每源观察和来源波次等下游门槛。

## 2026-07-20（土木工程情报 v2 工程基线收口）

- 将当前工作区中已完成的 #2–#13 纵向切片、已关闭或 superseded 的 SourceStream discovery/替代研究，以及 0037 campaign 与三份 Spec #1 前置 handoff 映射为单一可回滚工程基线；0037/handoff 不是关票或 GO 证据，父规格 #1 继续开放。
- 新增基线验收记录，固化文件归属、敏感信息复核、Issue #4 复验、全量/定向/迁移/Web 门禁与未闭环事项。仓库不包含 Owner 私有正文或真实逐条标注，所有研究态来源保持 disabled、无 SourceAdmission、无运行或覆盖信用。
- 修复累计纵向门禁的两个迁移终点回归：T05/T09 在保留各自升级-回滚-再升级断言后，把一次性测试数据库升至 head 供累计到 T12 的共享集成场景使用；同时将 T06 迁移与运行时必需的 v2 摘要 Schema 纳入 Python 镜像上下文。
- 全量 quality gate、fixture replay、T05/T06/T07/T08/T09/T11/T12、全部 discovery 定向测试与隔离正式栈 E2E/a11y 通过；未调用真实 AI、未启动公网采集、scheduler 或来源 worker，未产生 ENGINEERING/PRODUCTION GO。

## 2026-07-20（v2 T29R 第二批 W4 替代流发现）

- Issue #30 的中国建研院静态成果页与法律 blocker 证据保持原样，以 `SUPERSEDED` 收口；新 Issue #39 用新增候选 `RES-013`《建筑科学与工程学报》替换该第二批席位，并复用 `ENT-001` 中国交建，总机构数仍为二十个。
- 锁定期刊 `publicationIndexId=1474` 当前刊期 API、由返回刊期 ID 驱动的文章列表 API、精确 HTTPS 主机/路径/query allowlist，以及中国交建既有工程简讯 list/detail；保存点时公网、重定向、robots、条款、版权、访问边界和公开可达事实，未取得的 raw response SHA-256 保持 `null`。
- 期刊只产生 `RESEARCH_CONCLUSION`，同行评审或出版不冒充 `INDEPENDENT_VERIFICATION`；两流达到研究态 `BOUNDED + ADMISSION_READY`，但保持候选停用、无 SourceAdmission、无运行、无 PAUSE、无覆盖信用、无附件或公开再分发。
- 新增版本化 Schema、机器清单、5 项先红后绿测试、研究报告、验收记录和 `make t29r-source-discovery-test`。未产生 Owner Gold、DeepSeek 成功、真实准入、运行窗口或 GO，也未绕过 PublicationService、R3/R4、robots、版权、raw-first 和公网安全边界。

## 2026-07-20（v2 T31R 第二批 W5 替代流发现）

- Issue #32 的广联达与中国煤炭科工集团法律阻断证据保持原样，以 `SUPERSEDED` 收口；新 Issue #38 用既有 `GOV-017` 四川省住房和城乡建设厅与新增 `GOV-023` 贵州省能源局替换两个第二批席位，总机构数仍为二十个。
- 锁定四川住建科技栏目与贵州能源科技管理栏目，保存精确 HTTPS 集合/分页/详情边界、点时公网地址、零重定向、robots、条款导航、版权边界与真实响应 SHA-256；正向过滤只接受直接工程事实。
- 两流达到研究态 `BOUNDED + ADMISSION_READY`，但保持 `CANDIDATE + disabled`、无 SourceAdmission、无运行、无 PAUSE、无覆盖信用；`AUTHORITY_FINDING` 只限机关法定发布/评定边界，矿井瓦斯仍只归 `MINING`。
- 新增版本化 Schema、机器清单、10 项先红后绿测试、研究报告、验收记录和 `make t31r-source-discovery-test`。未产生 Owner Gold、DeepSeek 成功、真实准入、运行窗口或 GO，也未绕过 PublicationService、R3/R4、robots、版权和公网安全边界。

## 2026-07-20（v2 T20R 首批 W5 替代流发现）

- Owner 决定不再使用中国中铁与三一集团作为首批 W5，原 Issue #21 以 `SUPERSEDED` 收口而非伪装成原两流验收通过；首批组合改为既有 `ENT-002` 中国建筑与新增候选 `ENT-010` 徐工集团，总机构数仍为十个。
- 锁定中国建筑“企业动态”精确列表/分页/详情边界和徐工“施工案例”shell、固定 same-host POST 列表表单及详情边界；保存连接器、MIME、频率、限速、超时、策略版本、公网地址、重定向、robots、条款、版权、访问边界、UTC 核验时间和响应哈希。
- 中国建筑只产生 `PROJECT_FIRST_PARTY_RECORD`，徐工性能与效果只产生 `MANUFACTURER_CLAIM`；两流均排除无工程新事实内容、附件、图片、视频、全文和公开再分发，并保持 `desired_enabled=false`、`source_admission=null`、`actual_running=false`。
- 新增版本化研究 Schema、清单、基础设施行为测试和 `make t20r-source-discovery-test`；未执行真实准入或运行，未产生覆盖信用、Owner Gold、DeepSeek 成功、观察窗口或 GO，也未绕过 WAF、PublicationService、R3/R4、robots、版权和公网安全边界。

## 2026-07-20（v2 T29 中国建研院与中国交建流发现）

- 为 GitHub Issue #30 复用既有机构级 Source `RES-003` 与 `ENT-001`，保存 canonical alias、精确集合/静态候选入口、允许主机与路径、连接器、MIME、候选频率、限速、策略版本、内容正负边界、ClaimBasis 和点时合规证据；没有把中国交建简称/全称重复建源，也没有把根站、搜索结果或单篇新闻冒充集合。
- 中国交建限定为 `/news/jcxw/jx/` 稳定分页“简讯”列表及工程项目详情，达到研究态 `BOUNDED + ADMISSION_READY`；工程节点只允许 `PROJECT_FIRST_PARTY_RECORD`，效果、领先性和效益等企业自述只允许 `MANUFACTURER_CLAIM`，均不得升级为 `INDEPENDENT_VERIFICATION`。
- 中国建筑科学研究院旧 origin 已迁移到 `cabr.cn`；官网只有停留在十三五/2021 年的静态成果汇总，且法律声明禁止未经书面许可复制、传递或设置链接，与 raw-first 约束冲突，因此保持 `CANDIDATE + MANUAL_SHADOW`，记录 `NO_CONTINUOUS_COLLECTION` 与 `TERMS_PROHIBIT_COPYING`，不安排自动轮询。
- 研究清单显式保留未取得 raw response SHA-256 为 `null`，没有用浏览器 DOM、截图或 CCCC 边缘层 521 错误体冒充官方 raw 哈希。发现写能力仍只追加 SourceResearchDisposition；`desired_enabled=false`、`source_admission=null`、`actual_running=false`。
- 因 CABR 未达到 `BOUNDED + ADMISSION_READY`，Issue #30 保持 OPEN 且不解除 #31；本票未产生 Owner Gold、DeepSeek 成功、真实准入、运行窗口、PAUSE、覆盖信用或 GO，也未触碰 PublicationService、R3/R4 或降低 robots、版权和公网安全边界。

## 2026-07-20（v2 T25 中国土木工程学会流发现）

- 完成 GitHub Issue #26 的阻断替换：学会旧站仍因 HTTP-only 排除；标准流改用国家标准委组织、中国标准化研究院建设的全国团体标准信息平台，以 CCES 唯一机构 ID 固定过滤 73 条公开记录；根站、搜索、单篇材料、陈旧学术成果、会议宣传和会员活动均不冒充持续工程事实流。
- 保存 HTTPS 集合、固定 POST API/请求体、允许主机/路径、JSON/HTML MIME、日频候选值、超时/重定向/限速、策略版本及点时 DNS、TLS、robots、平台服务范围、版权、访问边界和五个响应 SHA-256。替代标准流达到 `BOUNDED + ADMISSION_READY`，使本票满足关闭条件；旧詹天佑奖流继续 `BOUNDARY_DISCOVERY + DISABLED`。
- 学会标准和奖励事实固定为 `PROJECT_FIRST_PARTY_RECORD`，不因学会身份升级为权威认定或独立验证；全文、表格、PDF、图片和附件不得再分发。第二批 W2 明确引用既有全国标准信息公共服务平台 `GOV-008-STANDARD-METADATA-CANDIDATE`，不重复其研究或授予准入。
- Schema 与机器清单升级为 v2，9 项失败关闭测试新增固定机构 ID、请求方法、MIME 与替代边界篡改保护；未追加 PAUSE、未授予覆盖信用，也未产生 Owner Gold、DeepSeek 成功、来源准入、运行窗口或 GO 证据，PublicationService、R3/R4、robots、版权与公网安全门槛保持不变。

## 2026-07-20（v2 T31 广联达与中国煤炭科工集团流发现）

- 完成 GitHub Issue #32 当前可诚实交付的研究纵向切片：广联达只锁定数智施工案例集合，中国煤炭科工集团只锁定“煤科硬核”分类集合；根站、搜索、全部案例、综合新闻、采购公告、外部媒体和单篇材料不冒充持续 SourceStream。
- 保存精确 URL、主机、路径/查询边界、HTML list-detail 连接器、MIME、日频、超时/重定向/限速、策略版本，以及 2026-07-20 的 DNS、HTTP、robots、条款、版权、公开访问和响应 SHA-256。内容门禁排除财报、品牌活动、经营新闻、泛 AI、党建、招聘及与工程无关制造内容。
- 两个流均达到 `BOUNDED`，但广联达协议禁止未经书面授权的爬虫/复制，中国煤科法律声明要求复制前取得书面许可；两者均与 raw-first 强制保存冲突，故保持 `MANUAL_SHADOW + DISABLED`，不标为 `ADMISSION_READY`，不追加 PAUSE，不授予覆盖信用，Issue #32 不能关闭或解除 #33。
- 新增版本化 Schema、机器可读研究记录、研究报告、验收记录、9 项失败关闭测试及 `make t31-source-discovery-test`。未产生 Owner Gold、DeepSeek 成功、来源准入、运行窗口或 GO，也未绕过 PublicationService、R3/R4、robots、版权或公网安全边界。

## 2026-07-20（v2 T27 中国公路学会与《隧道建设（中英文）》流发现）

- 完成 GitHub Issue #28 当前可诚实交付的研究纵向切片：在既有 `RES-001` 与 `RES-005` 下分别锁定中国公路学会工程成果动态集合和《隧道建设（中英文）》正式当前期；根站、搜索、单篇材料、会议宣传、会员活动和综合新闻不冒充 SourceStream 或工程事实。
- 保存精确集合、允许主机/路径、HTML 连接器、MIME、日频、超时/重定向/限速、策略版本及 2026-07-20 的 DNS、HTTP、robots、条款、版权、访问边界和响应 SHA-256。学会流形成 `BOUNDED + ADMISSION_READY` 研究输入，但仍无 SourceAdmission 或运行授权。
- 期刊官方站 HTTP/HTTPS 阻断事实继续保留并退出候选；替代流锁定万方 ISSN `2096-4498` 期刊专页及精确文章详情，保存有效 HTTPS、零重定向、robots 未发布、平台版权、公开题录/摘要与受限阅读下载边界。Reader 只保留题录、公开摘要和原链，不调用内部 API或再分发全文。
- Schema 与机器清单升级为 v2；两流现均为 `BOUNDED + ADMISSION_READY`，`closure_eligible=true`，Issue #28 已按 `completed` 关闭。19 项定向测试继续锁定隧道瓦斯 facet 必须同时具备 `TUNNEL` 与 `HIGHWAY` 或 `RAILWAY`；未追加 PAUSE、未授予覆盖信用，也未产生 Owner Gold、DeepSeek 成功、来源准入、运行窗口或 GO 证据。

## 2026-07-20（v2 T23 四川省交通运输厅流发现）

- 完成 GitHub Issue #24 的研究纵向切片：四川省交通运输厅仍只计 `GOV-015` 一个机构 Source，锁定科技与信息化、建设动态、质量监督和安全监督四个精确分页 `HTML_LIST_DETAIL` SourceStream；综合门户、建设管理聚合页、搜索和单篇材料均被排除。
- 保存 `jtt.sc.gov.cn` 固定路径、HTML MIME、每日一次/每分钟一次候选频率、超时与重定向上限、内容正负过滤、策略版本、UTC+8 核验时间、DNS/HTTP/robots/网站声明/版权证据及列表和样本详情响应 SHA-256。HTTP 未自动升级，故策略只允许 HTTPS；版权边界固定为题录、必要短摘、来源标注和原链，禁止全文再分发。
- 四流形成 `BOUNDED + ADMISSION_READY` 研究输入，并与既有 `GOV-007` 应急管理部事故调查报告流明确组成第二批 W1；四川地方工程事实与全国事故调查保持来源和法域分离。`GOV-015` 仍为 `CANDIDATE`、`desired_enabled=false`，无 SourceAdmission、运行、PAUSE 或覆盖信用。
- 新增版本化 JSON Schema、机器可读清单、研究报告、验收记录、六项失败关闭测试和 `make t23-source-discovery-test`。未产生 Owner Gold、DeepSeek 成功、真实来源准入、运行窗口或 GO，也未绕过 PublicationService、R3/R4、robots、版权或公网安全边界。

## 2026-07-20（v2 T16 水利部与国家能源局流发现）

- 完成 GitHub Issue #17 研究纵向切片：水利部改用官方政务服务平台 HTTPS 通知公告集合，只读取列表题录且不追随 HTTP 外链详情；国家能源局锁定煤炭司持续更新栏目。根站、搜索、单篇煤矿智能化文章和一次性汇编均不作为 SourceStream。
- 两条流保存精确集合、允许主机/路径、metadata-link 或 list-detail 连接器、MIME、日频、超时、零重定向、User-Agent、策略版本、领域预过滤以及 2026-07-20 的公网 IP、响应和法规证据哈希。水利只保留工程建设、监理、质量、安全、数字化和科技成果事实；能源只保留能源、矿山及工程装备生命周期事实。
- 两站 robots 404 按 RFC 9309 2.3.1.3 的 unavailable 规则核验；访问与保存严格限定为《政府信息公开条例》保障获取的主动公开政府信息及《著作权法》第二十四条允许的单一 Owner 个人非商业研究，禁止公开再分发。两流达到 `BOUNDED + ADMISSION_READY` 研究去向，仍无 Owner 启用、SourceAdmission、实际运行、PAUSE 或覆盖信用。
- 新增 metadata-only 失败关闭模型：该连接器必须没有详情 GET，`HTML_LIST_DETAIL` 仍强制详情观察；未知合规事实仍不得升级。未产生 Owner Gold、DeepSeek 成功、真实准入、运行窗口或 GO，也未绕过 PublicationService、R3/R4、robots、版权和公网安全边界。
- T16/T20 专项、全仓 lint/typecheck/test/contract-test/security-check/fixture-replay 与 quality-gate 等价组成项全部通过；完整结果见 T16 验收记录。

## 2026-07-20（v2 T18 中国民用航空局与《中国公路学报》流发现）

- 完成 GitHub Issue #19 的研究纵向切片：在既有 `GOV-014` 和 `RES-004` 机构身份下，分别锁定民航局机场司 `fl=60` 机构分类集合与《中国公路学报》正式当期目录，保存精确入口、主机、查询/路径边界、连接器、MIME、候选频率、内容过滤、策略版本和 UTC 合规证据。
- 民航局集合只接受机场规划、建设、运行、安全、监测、养护或工程装备事实，排除航班经营、时刻、旅游消费和一般经营新闻；期刊流固定 `RESEARCH_CONCLUSION`，只允许题录、官网公开摘要边界与原文链接，不再分发受保护全文。
- 官网当期目录显示 2026 年第 39 卷第 6 期，而公开“当期目录” RSS 仍返回 2023 条目，因此未把失真的 RSS 冒充当前更新流。新增版本化研究 Schema、机器可读清单、研究报告和四项基础设施行为测试。
- 两源均只获得 `BOUNDED + ADMISSION_READY` 研究去向，仍保持 `CANDIDATE`、`desired_enabled=false`、无 SourceAdmission、无运行、无 PAUSE、无覆盖信用；未产生 Owner Gold、DeepSeek 成功、真实准入、运行窗口或 GO 证据，也未绕过 PublicationService、R3/R4、robots、版权和公网安全边界。
- 本票专项测试与 Ruff 通过；按 Makefile 展开的 lint、strict typecheck、全量测试、contract-test、security-check、fixture-replay 和 quality-gate 组成项全部通过。共享 Trivy 快照的并发重建竞态以校验 1154 文件的冻结同内容快照复跑解决，未调整扫描器、严重级别或退出门槛。

## 2026-07-20（v2 T11 ReaderAppendix 治理附录）

- 完成 GitHub Issue #12 的只读纵向切片：FULL Reader 的底部附录默认折叠且首次展开才请求，覆盖未加载、加载、空、成功、错误、重试和重内容七种状态；折叠后复用已加载数据，错误与重试不遮蔽主阅读内容并恢复键盘焦点。
- 附录分组呈现 AcceptedClaims／证据、明确标注“不是证据事实”的自动结果、人工审核关系、自动关系、事故阶段和按时间倒序的结构化更正；存在安全 ReviewCase 时深链对应案例，否则回退 Owner 复核列表。阅读页未复制复核表单，v2 未新增纠正写接口，既有 v1 变更边界保持不变。
- 新增 `0044_t11_reader_appendix` security-barrier 治理视图与低权限授权：只暴露当前 FULL、R1/R2 权威组合，R3/R4、未决、失效及审核备注失败关闭；新增迁移往返验证、真实 PostgreSQL 组合读取/R3 404、严格契约、低基数读取指标、Nuxt 组件和浏览器/a11y 回归，以及 `make t11-reader-appendix-test`。
- 本票未生成 Owner Gold、未调用或宣称 DeepSeek 成功、未形成真实来源准入、运行窗口或 GO；未绕过 `PublicationService`、R3/R4、robots、版权或公网地址安全边界，也未降低门槛、删除断言或新增 skip。

## 2026-07-20（v2 T20 中国中铁与三一集团流发现）

- 为既有机构级 Source `ENT-003`（中国中铁）和 `ENT-009`（三一集团）分别锁定一个精确 SourceStream；没有把栏目虚增为新机构，也没有把根站、搜索结果或单篇材料冒充持续集合。版本化清单保存集合入口、允许主机/路径、HTML list-detail 连接器、MIME、日频上限、超时、重定向上限、User-Agent、策略版本与真实核验时间/响应哈希。
- 三一只保留 `/case/` 施工案例集合，要求施工机械同时出现既定工程对象与规划、施工、运营、养护、安全或监测事实，排除制造 ERP、灯塔工厂、产线改造和泛工业数字化；所有厂商参数与成效仅允许 `MANUFACTURER_CLAIM`，禁止提升为独立验证。
- 中国中铁只限定 `/web/xwzx61/zfgsdt39/` 子分公司动态集合，并以工程对象 + 生命周期正向门禁区分项目第一方工程记录与经营、党建、品牌宣传。但官网版权声明禁止未经许可把内容存入信息检索系统，与 raw-first 约束冲突，因此诚实保持 `BOUNDED + MANUAL_SHADOW + DISABLED`，等待书面许可，不标为 `ADMISSION_READY`，不追加 `PAUSE`。
- 发现服务的最小写能力只能追加 `SourceResearchDisposition`；清单固定 `desired_enabled=false`、`source_admission=null`、`actual_running=false`。本票未产生 Owner Gold、DeepSeek 成功、真实来源准入、运行窗口或 GO，也未触碰 PublicationService、R3/R4、robots、版权或公网安全门槛。

## 2026-07-20（v2 T14 住房和城乡建设部流发现）

- 实现 GitHub Issue #15 当前可诚实交付的纵向研究行为：把住建部公开目录的建筑市场监管 `F`、工程质量安全监管 `G` 和标准定额 `K` 固化为同一 `GOV-005` Source 下的三个有界 `LIST_DETAIL` SourceStream，记录精确入口、主题过滤、允许主机、路径边界、预期 MIME、候选频率和策略版本；门户首页与无过滤综合目录不作为流。
- 保存 2026-07-20 点时公网、HTTP→HTTPS、详情与同主机 PDF 重定向证据，并核验站方未发布 `robots.txt`、公开目录/网站地图/官方导航未链接独立自动化访问条款、页脚转载须注明来源。三个精确流达到 `StreamReadiness=BOUNDED`、`SourceResearchDisposition=ADMISSION_READY`，满足 Issue #15 的研究票关闭条件。
- 明确后续 W2 使用住建部 `GOV-005-G` 与既有国家矿山安全监察局通知公告流配对；矿井瓦斯保持 `MINING`，不授予 `TUNNEL_GAS_MONITORING` 覆盖信用。
- 新增版本化 Schema、机器可读研究记录和四项基础设施测试；`ADMISSION_READY` 只允许进入后续 SourceAdmission Probe，不把 404 robots、未链接独立条款或转载声明解释成采集许可。未改变 `desired_enabled`、SourceAdmission 或运行状态，未追加 `PAUSE`，未执行真实采集或准入波次，也未产生 Owner Gold、DeepSeek 成功、运行窗口、覆盖信用或 GO 证据。
- 本票专项 pytest 与 Ruff、全仓 typecheck、contract-test、security-check、fixture-replay 通过；完整门禁结果见 T14 验收记录。

## 2026-07-20（v2 T12 许可媒体与附件安全交付）

- 完成 GitHub Issue #13 的纵向切片：媒体登记只接受服务端从当前 `CLEAN` 附件、raw 对象、成功采集尝试、原始 URL 哈希和许可证据读取的权威事实；客户端上送哈希、扫描状态或许可声明不能成为发布依据。图片在严格字节数、像素数、实际 MIME 和解码边界内重新编码为内容寻址 PNG，Reader 永不把原始媒体对象或任意远程 URL当作预览。
- `PublicationService` 仅向 FULL 投影当前仍满足许可与三重 `CLEAN` 状态的同源预览和下载动作；R3 不含媒体，R4 普通读取仍为 404。无再分发许可的材料只保留名称和原站链接；有再分发许可的附件也必须在下载时重验当前事实，随后才返回不超过 300 秒的私有对象签名地址。
- 新增 `0045_t12_media_delivery` 权威读取函数、写入触发器和 security-barrier 阅读视图；对象缺失失败关闭为 404，存储暂时失败返回不泄漏内部信息的 503，扫描状态变化立即撤销预览和下载。新增真实 PostgreSQL/私有 MinIO 纵向回归、迁移往返、桌面/移动端与 axe 回归及 `make t12-media-delivery-test`。
- 本票未生成 Owner Gold、未调用或宣称 DeepSeek 成功、未形成真实来源准入、运行窗口或 GO；未绕过 `PublicationService`、R3/R4、robots、版权、重定向与公网地址安全边界，也未降低门槛、删除断言或新增 skip。

## 2026-07-20（v2 T08 证据优先搜索与统一 Feed／Card）

- 完成 GitHub Issue #9 的纵向切片：`/api/v2/search` 继续只消费 `PublicationService` 物化的 v2 投影；标题、来源、当前 AcceptedClaims 与 `SourceExcerpt` 使用 A 级主权重，`AISummary` 仅使用 D 级低权重，并增加安全转义的连续中文子串召回。证据子串排名增量为 AI 的 1000 倍，AI 不能冒充主召回来源。
- FULL 搜索结果新增受控 `search_explanation`，逐项说明标题、来源、AcceptedClaims、原文摘录命中及 AI 低权重辅助；R3 契约未扩展，搜索 Card 仍只显示服务端元数据白名单。首屏空游标显式转换为 PostgreSQL `bigint`，避免 asyncpg 类型推断失败。
- 正式 Nuxt 的首页、筛选 Feed、热点与搜索继续复用 `IntelligenceFeedPage`、`TimelineFeed`、`IntelligenceCard` 和统一 `/events/{id}` Reader。FULL Card 显示两行原文摘录和两行真实摘要／状态文案；AI 非成功不再隐藏摘录；没有新增演示总结、演示评分、热点总分或模糊“可信度”。
- 新增契约、服务、真实 PostgreSQL durable search、组件和正式浏览器／axe 回归，以及 `make t08-evidence-search-test`。测试只使用协议等价 fixture；未生成 Owner Gold、未调用或宣称 DeepSeek 成功、未准入来源、未形成运行窗口或 GO，PublicationService、R3/R4、robots、版权与公网安全边界保持不变。

## 2026-07-20（v2 T10 Owner Reader B 统一详情页）

- 完成 GitHub Issue #11 的正式 Nuxt/Vue 详情页纵向切片：标题区横跨页面，1024px 起使用证据正文主栏与无嵌套滚动的 sticky 来源上下文侧栏，窄屏按来源上下文、SourceExcerpt、AISummary、媒体材料、单一 ReaderActions 和折叠附录的固定语义顺序回流。
- FULL 独立呈现 PrimaryType/facets、ClaimBasis、来源官方性、人工复核状态、两个可空时间、热点触发理由、原文摘录、结构化 AI 事实/判断、许可媒体和更正提醒；热点不显示总分，官方一手来源不与人工复核合并。
- Reader 使用服务端七态 `status_message`，SUCCEEDED 事实段显示 AcceptedClaim 引用，判断段明确标为“AI 判断”；STALE 与更正提醒关联，任何 AI 降级均不隐藏来源与 SourceExcerpt。R3 只消费安全元数据，R4/未决/claim 失败继续由服务端 404。
- 新增单一响应式 `ReaderActions` 与正式 Playwright/axe 验收，覆盖 320、640（200% 等价）、768、1024、1280、1440、1920px、超长标题/来源、无横向溢出、键盘焦点、屏幕阅读器语义和减少动画；未引入原型、React、第二组件库或演示分数。
- 本票未生成 Owner Gold、未调用或宣称真实 DeepSeek 成功、未形成真实来源准入、运行窗口或 GO；PublicationService、R3/R4、robots、版权和公网安全边界未改变。

## 2026-07-20（v2 T06 DeepSeek 运行、摘要状态与自动补偿）

- 完成 GitHub Issue #7 的纵向切片：非测试环境只允许固定 DeepSeek provider；版本化服务端 profile 映射到目录模型 `deepseek-v4-flash`，真实请求与回调分别重验 SourceAdmission、Owner/来源运行意图、当前文档、raw 安全、执行域、激活配置和预算。
- 将“已配置”与“可用”拆开；可用性要求 60 秒内心跳、队列/预算健康、provider/model 匹配及 24 小时内真实获准内容 Schema 成功。probe、canary、Secret 和 CI stub 均不能写入该成功事实；本轮仅确认本地 Compose Secret 文件存在，未调用或宣称 DeepSeek 成功。
- 新增独立 SourceExcerpt、七态摘要事实和 PublicationService 专属刷新 outbox；AI 失败不再隐藏已过门禁的来源与摘录，恢复后执行 5/15/45 分钟、两小时封顶的持久补偿。Schema 永久失败不重试，重复 callback/刷新不会重复候选、状态、发布决定或物化投影。
- 新增 `0041_t06_ai_runtime_projection` 隔离迁移回放、受限原始/结构化结果与成本追踪、低基数指标/告警、确定性服务端文案、Nuxt 状态消费及 `make t06-ai-runtime-test`。未生成 Owner Gold、来源准入、运行窗口或 GO，未绕过 PublicationService、R3/R4、robots、版权或公网安全边界。

## 2026-07-20（v2 T09 永久热点授予）

- 完成 GitHub Issue #10 的热点纵向切片：模型只能提交引用当前 claims 的严格候选；`PublicationService` 从 PostgreSQL 当前分类资格、AcceptedClaims/证据、SourceAdmission、来源机构/转载谱系、发布时间和服务端评分事实计算资格，模型、客户端和后台按钮均不能直接授予热点。
- 固定 `hotspot-v2.0.0` 五项权重与 70 分门槛；仅“7 天内至少两个去重后的独立合格来源”或“单个权威一手来源且总分至少 70”可追加 Award。三种 `PrimaryType` 均可独立获热点资格，授予不会改写主类型。
- 新增追加不可变的候选、评估输入快照和永久 Award 事实；重评或规则升级只追加，不覆盖或撤销历史。普通 Feed/热点页仅展示触发路径、独立来源数和由当时 AcceptedClaims 支持的理由，不投影总分。
- 新增 `0043_t09_hotspot_awards` 隔离迁移回放、真实 PostgreSQL 权限/不可变 seam、低基数指标与拒绝告警，以及 `make t09-hotspot-test`。测试中的 SourceAdmission、评分和模型候选均明确为一次性协议 fixture，不构成 Owner Gold、DeepSeek 成功、真实来源准入、运行窗口或 GO；PublicationService、R3/R4、robots、版权与公网安全边界保持不变。

## 2026-07-20（v2 T07 SourceAdmission 与受控影子采集）

- 完成 GitHub Issue #8 的流级失败关闭切片：`Source` 继续按机构计数，`SourceStream` 表示机构下的有界集合路径；研究 disposition、Owner `desired_enabled` 意图、服务端 SourceAdmission 决定和实际影子运行分别保存为四类追加式事实。
- SourceAdmission 逐流要求公网安全、robots、条款、版权、访问边界、限速、预算、质量、熔断和运行门禁全部明确通过，并绑定最长 24 小时有效期；任一未知、失败、过期、Owner 撤权、人工停用或流未就绪都会由数据库安全函数保持 `PAUSED`。
- 新增统一 `SourceAdapter` 受控影子编排：请求前复核授权，响应字节、元数据与服务端 SHA-256 先进入 raw 持久边界，再按实际 MIME 分流 HTML、PDF、RSS；解析失败保留 raw，成功后只交接 DocumentVersion ID 到既有 qualification/outbox 链，未新增 Event、claim 或发布旁路。
- 新增 `0042_t07_controlled_stream` 的 `0041 → 0042 → 0041 → 0042` 隔离迁移回放、真实 PostgreSQL 流级授权 seam、低基数控制/采集指标和 `make t07-source-shadow-test`。所有准入和运行数据均为一次性测试事实；本票未生成 Owner Gold、未调用或宣称 DeepSeek 成功、未准入或启用真实来源、未形成真实运行窗口或 GO，PublicationService、R3/R4、robots、版权与公网安全门槛保持不变。

## 2026-07-20（v2 T05 Reader 发布投影）

- 完成 GitHub Issue #6 的后端纵向切片：只有已经持久化分类资格、当前文档版本、当前 accepted claims、有效证据和当前内容候选才能由 `PublicationService` 重建 `/api/v2` Reader 投影；普通读取只返回 FULL 或严格 R3 元数据，R4、未决和失效内容保持 404。
- FULL 投影分开呈现来源官方性与人工复核状态，保留可空原文发布时间/首次发现时间、连续原文摘录、结构化事实/AI 判断摘要、claim basis、热点原因、版权许可媒体、附件与证据附录；R3 响应由严格契约限制为安全白名单。
- 新增 Owner-only R4 隔离投影、追加式资格/发布决定/v1 逐行归档哈希事实、低基数发布结果指标和安全失败告警，以及 `0039 → 0040 → 0039 → 0040` 隔离迁移回放；真实 PostgreSQL、Redis 和私有 MinIO seam 验证 FULL/R3/404、重试无物化重复、媒体读取和 v1 汇总 SHA-256。
- 本票不复活 v1 Reader，不允许复核命令写发布状态，也未生成 Owner Gold、调用或宣称 DeepSeek 成功、改变来源准入/运行状态或形成 GO；robots、版权、R3/R4 和公网安全门槛保持不变。

## 2026-07-20（v2 Owner Gold pilot／生产校准拆分）

- 父 Spec #1 将 20 条 Owner 人工试标明确为不授权自动通过的流程 pilot；#3 以 `PILOT / SUPERSEDED` 关闭，不宣称试标完成、DeepSeek 成功、来源准入、运行窗口或 GO。
- 新建 #36 承接原 360 条生产级 Owner Gold、独立预测、阈值校准、服务端安全入库和耐久消费要求，并将 #14 的原生 blocker 从 #3 迁移到 #36。
- 既有生产校准器、90% precision/recall、锁定负例零泄漏及失败关闭约束保持不变；20 条 pilot 固定 `authorizes_auto_pass=false`。
- 完成私有 20 条 HUMAN_OWNER pilot 的 reviewed-artifact、manifest 与结构化 JSONL 交叉校验：20/20 哈希和字节数一致，十一对象、交通隧道瓦斯和施工机械覆盖通过；结果为非生产 `PILOT_PASS`，无自动通过授权，也不形成来源、模型、运行窗口或 closeout GO 证据。

## 2026-07-19（v2 T04 证据化内容准备）

- 从当前文档版本的 active `AcceptedClaim` 生成单段连续、最长 500 字的 `SourceExcerpt`，并通过严格 Schema 接受 300–500 字、分为“发生了什么 / 工程影响 / 局限与后续”的结构化摘要候选；事实段必须双向引用当前 claims，判断段显式标记为 AI 判断。
- 新增追加式 `0039_t04_content_candidates` 候选与失效事实、Owner-only 复核投影和协议等价 stub 边界；文档版本、accepted claims、撤回或更正变化均使旧候选失效，事实决定与 AI 摘要决定分开保存。
- 模型调用只接收最小 accepted claims 与证据摘录，并在调用前执行 prompt-injection 与敏感值扫描；模型响应依次通过 JSON Schema 与 Pydantic 校验，失败关闭。该切片不写发布投影，也不改变 `PublicationService`、R3/R4、robots、版权、公网安全或来源运行授权。
- 仓库未生成 Owner Gold、未调用或宣称 DeepSeek 成功、未形成来源准入、运行窗口或 GO 证据；协议 stub 和固定测试数据只证明契约行为。

## 2026-07-19（v2 T02 Owner Gold 阈值校准）

- 新增私有 Owner Gold 校准入口，严格校验 180 正例、90 边界例、90 锁定负例、三主类型、十一工程对象、隧道瓦斯监测和施工机械覆盖，以及逐条 `HUMAN_OWNER`、UTC 标注时间、双 SHA-256、证据定位、规则/模型/prompt 版本。
- 自动通过阈值改为从候选预测的实际置信分布搜索；precision/recall 均至少 90% 且锁定负例零泄漏时才生成版本化 `GO` 事实，缺失、篡改、版本错配或指标失败均生成 `NO_GO`，不再把 0.90 常量当成批准门槛。
- 新增追加式 `0038_owner_gold_calibration` 事实表及最小读取权限；qualification 无校准时进入复核，production SourceAdmission 保持 `PAUSE`，PublicationService 只读精确版本授予，production closeout 校验并记录事实哈希、阈值和版本。
- 仓库未保存、生成或提交真实 Owner 私有语料或校准 `GO` 文件；协议 fixture 明确为 `TEST_FIXTURE_ONLY`，不能作为 Owner Gold、DeepSeek 成功、来源准入、运行窗口或 closeout GO 证据。
- 修复并行 T04 改动暴露的严格类型边界并重新生成契约后，全仓 lint、typecheck、test、contract-test、security-check、fixture-replay 与 quality-gate 全部通过；私有数据根、验收 evidence root 和当前 PostgreSQL 仍无 Owner Gold 校准事实，故保持自动通过禁用且不关闭 #3。

## 2026-07-19（Issue #4：首页搜索优先入口）

- 实现土木工程情报 v2 首页搜索纵向切片：搜索区域在 DOM 和视觉顺序上均位于“今日精选”一级标题与时间线之前，且 `/selected`、`/all`、`/digital`、`/safety`、`/industry`、`/hot` 不重复渲染首页搜索。
- 为搜索 landmark 增加由可见标签提供的唯一可访问名称，并为复用组件生成唯一 label/input 关联；搜索结果加载状态改为明确的“正在加载搜索结果”，既有空结果、Problem Details 错误和排序行为保持不变。
- 新增正式 Playwright 验收，覆盖非空时间线的 DOM/几何顺序、过滤页唯一性、加载/空/错误状态、键盘焦点、屏幕阅读器名称、200% 等价回流和 axe；未新增 skip，未使用 Owner Gold、真实来源或 DeepSeek 证据。
- 2026-07-20 在后续共享工作区快照上完成最终复验：全仓 lint/typecheck、全量测试、契约、安全检查、正式 Nuxt 构建、`74` 条 Web E2E 与 `21` 条 a11y 全部通过，原票外 lint 阻塞已消除；GitHub Issue #4 随后关闭。

## 2026-07-19（v2 T01 领域分类失败关闭）

- 完成 GitHub Issue #2 的分类纵向切片：分类契约固定十一类工程对象、唯一主类型、三轴 facets 和受控内容形态，并在服务端统一校验交通隧道瓦斯组合、施工机械生命周期事实和证据块定位。
- 在现有 AI 内容准备链路增加锁定负例二次门禁；中医药/泛健康、旅游消费、金融行情、泛 AI、无工程事实的港口经营以及工程机械企业 ERP/生产线/泛工业互联网内容即使被模型标为相关，也只形成 metadata-only `QualificationReviewCase`，不会进入抽取、Item/Event 或阅读投影。
- 新增版本化结构回放报告与 CLI；报告固定标记 `STRUCTURAL_REPLAY` 和 `authorizes_auto_pass=false`，不得作为 HUMAN_OWNER Gold、真实来源、DeepSeek 成功或生产 GO 证据。
- 增加低基数分类决定与 PostgreSQL OPEN 复核积压指标；复核 case 重试采用冲突不改写并返回既有 case，不绕过 PublicationService、R3/R4 或来源运行边界。

## 2026-07-19（土木工程情报 v2 tracer-bullet tickets）

- 将正式 Spec [#1](https://github.com/flyingTurkey/codex/issues/1) 拆分为 34 张可在全新 Codex 上下文中执行的纵向 tickets [#2](https://github.com/flyingTurkey/codex/issues/2)–[#35](https://github.com/flyingTurkey/codex/issues/35)，统一添加 `ready-for-agent`，并建立与批准依赖图一致的 GitHub 原生 `blockedBy` 关系；未运行 triage，也未修改父 Spec。
- 来源扩充拆为 SourceStream 边界发现、双源真实准入波次、首十源连续 14 天和二十源组合收口；分类内核与 360 条 Owner Gold 分离，禁止生成语料冒充 `HUMAN_OWNER` 证据。
- 发布后完成依赖、标签、父引用、UTF-8 正文、来源门禁和 UI 验收的独立回读；修复最初 PowerShell 管道导致的中文正文编码损坏，并将首页搜索顺序校正为“搜索 → 今日精选标题 → 时间线”。

## 2026-07-19（土木工程情报质量与阅读体验 v2）

- 将完整产品改造 Spec 发布为 GitHub Issue [#1](https://github.com/flyingTurkey/codex/issues/1)，仅添加 `ready-for-agent` 标签；Owner 确认以 Gold Corpus 领域 seam、durable 后端纵向 seam 和正式 Nuxt 浏览器 seam 作为三个顶层测试边界。Spec 明确保持当前 engineering/production `NO_GO`，不把规格就绪误报为来源、AI 或生产切换就绪。
- 使用三个独立只读审查轴完成共同理解收口：Owner 确认十一类 `EngineeringObject` 为产品边界，六类仅为本轮来源覆盖子矩阵；清除来源报告中的数字成熟度产品门禁和港航误排除，明确 B 方案尚待正式重建，并新增总体与 Owner Reader 两份 `to-spec` 交接成果。产品规格现为 READY，工程与生产 closeout 仍保持 NO_GO。
- 将 AI 诊断、来源研究和 Owner Reader 原型的已确认结论并入共同理解：Acquisition 增加来源相关性、流成熟度、法域角色和研究处置语言，Evidence & AI 明确运行授权、真实 Schema 成功、AI 可用性与耐久内容交接；验收记录同步 Owner 已确认的 B 方案及其正式重建边界，未新增 ADR 或改动业务代码。
- 新增 `0037_engineering_closeout_campaign` 及可按 campaign ID 恢复的 `prepare/start/status/finalize` 工程验收活动；活动事实 append-only、有事实时阻断降级，并保存环境切换、来源观察、AI canary、故障注入、Feed 审计、只读归档预检和最终恢复结果。
- 新增固定 20 个官方公开来源的工程活动清单；缺少的 5 源只登记为 `CANDIDATE_ONLY`，20 源可在隔离 acceptance 环境并行观察，但不会改变 Owner 运行意图、生产 `ACTIVE` 状态或发布边界。
- 来源工程样本固定使用 campaign 启动 cutoff 和去重后的当前文档版本；新增 `hard_negative_evaluated` 完整性硬门禁，缺少耐久 locked-negative 评估时即使观测泄漏数为零也保持 `PAUSE`。
- 工程证据导出器从 PostgreSQL、对象存储和真实 v2 投影生成运行、来源、Feed、补偿、历史预算对账、归档及 context 证据；acceptance-only 故障注入在真实调用门禁不成立时失败关闭，不制造 DeepSeek 成功或发布副作用。
- 完成 campaign `019f79e1-5d04-73e5-880b-ab9ce5fb37f7` 的真实一小时活动及环境恢复：九项仓库门禁和 20/20 来源结论通过，归档预检保持只读；因 observation gap、余额未知、无真实 Schema 成功、无 200 条 Feed 和未完成补偿验收，engineering readiness 如实为 `NO_GO`。
- 新增并完成对抗性复核的 [土木工程情报平台权威数据源扩充方案研究报告](docs/research/2026-07-19-civil-engineering-authoritative-source-expansion.md)：基于官方一手来源评估 36 条国内与国际候选，在十一类产品对象边界内重点研究六类对象及瓦斯监测/施工机械跨切面，独立记录相关性、流成熟度与法域角色，并把后续工作拆为准入核验、边界发现和人工影子队列；研究子矩阵不缩窄产品范围，也不构成来源准入、启用或采集授权。
- 修复“DeepSeek 已配置但无内容结果”的真实运行断点：新增 `0036_ai_content_result_lifecycle`，将终态 pipeline 与 durable content outbox 原子收口，迁移历史伪 `WAITING_AI`；callback 在读取步骤输入前复核授权，撤权时不消费模型输出、不进入 repair，但结算可验证的真实 Token/费用元数据并记录 `AI_RUNTIME_AUTHORIZATION_DENIED`。同时修复 runtime probe 的 PostgreSQL 时间参数类型和模型目录映射，使 Owner 页面准确区分“已配置”“运行健康”和“最近真实 Schema 成功”。
- 新增 ADR-0003 和显式双验收 profile：`ENGINEERING_CLOSEOUT` 使用 1 小时 AI/来源窗口、一次真实 Schema 成功和无人工标注的 200 条服务端 Feed 结构审计；`PRODUCTION_CLOSEOUT` 完整保留原 24 小时、Owner gold、人工 Feed precision、72 小时/14 天门槛。两者均保留合规硬门禁、补偿验收和只读归档预检。
- `make intelligence-v2-closeout ACCEPTANCE_PROFILE=engineering|production` 现在必须显式选择 profile；readiness manifest 记录独立规则版本，同一小时证据只能使 engineering 通过，不能使 production 通过。
- 追加 `0035_intelligence_v2_closeout`，以 append-only 事实保存 Owner 复核重处理 Outbox、AI 运行观察、AI 补偿运行和来源准入评估；有事实时阻断破坏性降级。
- Owner 决定改为按 `command` 判别的严格联合契约，接口在同一事务中追加决定与 Outbox，返回可幂等重试的 `202/QUEUED` receipt；Worker 只传递 Outbox ID，最终统一进入 `PublicationService.refresh_v2_projection`。
- v2 Feed、搜索和热点补齐 surface-bound、版本化的不透明 keyset cursor；复核 list/detail 使用正式契约，v2 错误统一为带稳定原因码的 Problem Details。
- 迁移 10 个旧阅读 Playwright spec 到 `/api/v2/feed|search|hotspots|events`，合法的 saved/daily、引用、版本 diff 和关系纠正仍保持 v1，被替代的 v1 reader 保留 404 回归。
- 新增 30 秒无网络 AI runtime probe、6 小时固定公开文本 SHADOW canary、真实成功/外部余额观察、5/15/45 分钟且两小时封顶的补偿策略与持久事实；canary 只在验收类环境、当前来源/DocVersion/raw CLEAN/预算门禁全部通过时调用，结果不进入发布链。Secret 已配置不再被界面误报为真实可用。
- 将生成的 `GoldCorpus` 更名为结构回放语料；新增 360 条 Owner qualification、200 条 Feed 抽检和 20 源准入的私有证据校验器，强制 `HUMAN_OWNER`、内容/原始对象哈希、固定规则版本、波次时间和服务端重算阈值。
- 新增 `make intelligence-v2-closeout`，生成经 Schema 校验和 SHA-256 封签的 readiness manifest；当 24 小时、人工标注、来源观察或只读归档预检证据缺失时稳定非零退出并输出 `NO_GO`。
- 新增土木工程直接相关性、三主类型、十一工程对象、隧道瓦斯监测与施工机械 facets 的 v2 严格契约；R3 只能返回安全元数据，R4 和未决内容在普通读取面不可见。
- 采集处理改为 raw-first 与 MIME 分流，分类门禁先于事实抽取和 Event 创建；旧 personal signal 不再复活 Event 或向 R3 注入 claims、证据和自动处理结果。
- 新增空的 v2 投影代际、append-only Owner review、版本化 AI summary、永久热点授予、媒体权利和证据优先搜索迁移，以及 `/api/v2` 阅读与复核 API。
- 正式 Nuxt 首页改为“今日精选”并前置搜索，新增行业视图、无可见总分的热点榜单、阅读优先详情和折叠附录；Feed、Timeline 与 Card 继续复用。
- 生产环境禁止 mock AI provider，HTML/PDF 按 MIME 解析；DeepSeek 的“已配置”与真实可用性仍须由运行态 heartbeat 和 24 小时真实成功证据判定。
- 建立四个 bounded context、CONTEXT-MAP 与 ADR-0002；不自动启用新来源，不把生成样本冒充人工 gold corpus。

## 2026-07-19（Agent skills 仓库配置）

- 为 `flyingTurkey/codex` 固化 GitHub Issues 工作流、默认五项 triage 标签和 multi-context 领域文档消费规则，并验证仓库端五项标签全部可用，供 `to-spec`、`to-tickets`、`triage`、`qa`、`grill-with-docs` 与相关工程 Skills 复用。
- 在根 `AGENTS.md` 增加统一入口，并新增 `docs/agents/` 配置文档；未创建空的 `CONTEXT-MAP.md` 或上下文文档，领域术语和决策仍由 `domain-modeling` 在实际确认后按需生成。

## 2026-07-19（个人界面优化）

- 将已确认的首页、来源中心和情报详情推荐稿落实到正式 Nuxt 界面；继续复用权威设计令牌、Iconoir 和既有共享组件，没有引入第二套组件库或演示数据。
- 首页改为“今日情报”个人研究工作台，首屏展示真实情报数、健康来源、采集投影状态和自动发现状态；窗格使用克制的牛油果低饱和渐变。
- 来源中心把添加 URL、真实健康概览和来源卡移到首屏，自动发现设置收进原生可访问折叠区；修复 `server:false` 数据加载造成的 hydration mismatch。
- 情报详情不再把数字化政策误标为安全案例生命周期；两条 accepted claims、Evidence IDs、定位方式和 SHA-256 直接进入证据首屏，安全案例专属字段只在安全案例中显示。
- 全局交互使用 140–180ms 令牌化颜色、阴影和按压反馈，并继续尊重 `prefers-reduced-motion`；同步更新桌面/移动端截图、视觉基线和 Design QA。

## 2026-07-19（试点正式重判、AI 费用桥接与界面审查准入）

- 固定五源试点策略版本 `pers10-fixed-five-3of5-v1` 在来源集合精确匹配、真实端到端证据链和全部安全不变量通过时，允许 3/5 作为正式 `PASS`；默认及未来试点仍保持 4/5 正式门槛，3/5 仍为 `LIMITED_PASS`。
- 对不可变 7200 秒运行 `019f75ae-4fba-76d4-bc0f-3fb1744eaa86` 执行无联网复核：50 次请求、1,745,429 字节、13/13 原始哈希、16/16 Evidence IDs、0 条无证据关键事实、0 条未验证 AI 事实索引和停用后 0 次联网均保持不变，正式结论为 `PASS`。
- 两条失败来源保存了应急管理部公开目录、交通运输部静态政策目录候选；候选必须重新通过有界 Probe，不能继承本次通过状态。
- 新增 `0033_controlled_ai_budget_bridge`，在同一 PostgreSQL 事务中把现有 AI 月度积分预留与受控运行 1.25 美元（按保守 8 元/美元上界即 10 元）费用上限联动；未知账单按预留额结算，超限、非运行态和损坏降级均失败关闭。
- Worker 对受控 AI pipeline 使用新桥接函数；迁移专项已验证 `0030 → 0031 → 0032 → 0033 → 0032 → 0030 → 0033` 和有受控 AI 事实时拒绝降级。
- 将 `fontless` 的 `esbuild` 定向固定到已修复的 `0.28.1`，`pnpm audit --prod` 漏洞计数为 0。
- 修复真实个人信号详情仍依赖旧发布投影的问题：metadata-only 详情现在由个人信号补齐 accepted claims、Evidence IDs 和自动处理结果；Feed 按事件合并旧 metadata 与新证据信号，避免同一事件重复展示。
- 历史测试来源改为显式 `FIXTURE_TEST`/`FIXTURE_REPLAY` 隔离；业务来源列表和 PublicationService backfill 不再读取这些记录，同时不以 `.test` 域名猜测数据性质。修复前数据库备份 SHA-256 为 `D3AE6EC0567D72ED1DC2D261F8E7E50922FE992EDC3D27F403D1E38A040F2065`。
- 完成首页、来源中心和情报详情的只读界面审查与唯一推荐候选图；原始审查材料保存在 `D:\SRBGData\reports\ui-review\core-pages-20260719T0225Z`，随后经 Owner 确认进入正式实现。

## 2026-07-18（受控真实试点探测与收尾补强）

- 新增 `0031_controlled_personal_runs`，把两小时个人试点的 80 次物理 HTTP、150MB 总响应、50MB 单响应、10 次/30% 失败熔断、四小时墙钟以及精确来源路径边界固化为 PostgreSQL 权威账本；新请求在 `STOPPING` 后失败关闭，已预约请求必须结算后才能结束。
- 来源探测和生产抓取共用物理请求观察器；重试与重定向逐次记账，同域一分钟限速由数据库串行校验，受控 `fetch_run` 自动继承试点 ID。未接入同等耐久费用账本前 DeepSeek 在试点中明确降级关闭，禁止 mock 结果冒充真实 AI。
- 新增 `make personal-pilot-control-test`，在一次性 PostgreSQL 中执行 `0030 → 0031 → 0030 → 0031`，并验证有事实时拒绝降级、路径越界拒绝、响应字节结算与网络对端异常记账。
- 首轮受控真实试点在 12 个请求、173,268 字节、0 传输失败时因四个来源均无法识别采集流而以 `SOURCE_RELIABILITY_GATE` 失败关闭；五来源全部停用，4 个真实原文对象哈希复核 100%，未进入事实或页面投影。结果保存在 D 盘并记录于 `docs/acceptance/personal/controlled-real-pilot.md`。
- 通用 HTML 探测器现可从普通 `div`、`li`、`table` 列表识别有标题的同域 HTTPS 详情链接，并拒绝隐藏元素、导航噪声、query/fragment、跨域和来源路径前缀外链接；HTTP 重定向、同域 canonical 与严格零延迟 meta refresh 仍受相同边界约束，JavaScript 跳转稳定返回 `UNSUPPORTED_CLIENT_REDIRECT`。
- 受控列表流每周期最多抓取 5 条唯一详情，试点账本维持精确主机一分钟一次物理请求、每来源一小时调度与全部预算/熔断限制；来源画像任务在 AI 明确停用且回调失联达到上限时，从已持久化真实探测证据生成 `PARTIAL/MODEL_RESULT_TIMEOUT`，不调用模型、不伪造摘要。
- 修复后真实试点 `019f75ae-4fba-76d4-bc0f-3fb1744eaa86` 跑满 7200 秒，以 50 次已结算请求、1,745,429 字节、1 次传输失败和 AI 零调用/零费用完成。中国政府网、交通运输部、四川省交通运输厅 3/5 完成正常采集周期，形成 13 个有效原始哈希、7 条内容、16 个 accepted claims/Evidence IDs 和 7 个 PublicationService 投影；关键事实无证据及未验证 AI 事实索引均为 0，停用后新增联网尝试为 0。
- 原始失败报告保持不可改写；独立只读复核报告给出 `LIMITED_PASS`，因此安全收尾但不进入界面候选图。应急管理部事故调查入口和交通运输部信息公开根入口因脚本跳转失败；下一轮可优先评估应急管理部公开目录与交通运输部政策解读静态目录，但未经新预检和真实试点不得计为通过。

所有重要变更记录在此文件。

## [Unreleased]

### PERS-10 旧企业治理退场与个人模式收口

- 将 PostgreSQL/WAL、两套 MinIO、Redis、Prometheus 和 Grafana 的持久化数据切换到 `D:\SRBGData\srbg-data.vhdx` 的 ext4 文件系统；启动前自动挂载并验证七个目录，失败时拒绝 Compose 启动。切换使用经过数据库/对象/缓存/观测隔离恢复验证的备份，原 Docker named volumes 保留不删除；本机试点配置明确关闭自动来源发现。
- 新增 `0030_pers10_role_archive_repair`：为 `srbg_admin_role`、`srbg_model_role` 和遗漏的 `srbg_source_governance_writer` 保存可校验角色快照，兼容已应用 0029 但缺失角色记录的数据库；跨数据库依赖、角色状态、数量或哈希异常时失败关闭，降级按 `0030 → 0029 → 0028` 精确恢复授权。
- 新增 `0029_legacy_governance_retirement`：在单事务中保存规范化逐行 JSON/SHA-256、分类计数与汇总 SHA-256，验证后把 52 类旧治理关系移入只读 `legacy_governance_archive`；数量或哈希不一致时拒绝退场或降级。
- 降级在恢复任何表之前验证完整归档，并恢复原表、数据、约束、触发器、授权和 0029 前双路径调度函数；新增迁移回滚 Runbook、备份恢复说明和 `make personal-migration-test`。
- 产品身份只保留固定本地 Owner；旧 Admin API、企业角色、企业后台任务、企业页面/组件和生成契约退出运行时，个人 AI 设置迁至 `/settings/ai`，旧路由只重定向到 `/sources` 或返回不可用。
- 迁移仍适用的证据、PublicationService、安全、数据完整性和无障碍测试；固定评估为来源主题准确率 83.33%、健康原因/Evidence ID 100%，关键数字/日期无证据、未验证 AI 事实索引和新增人工审核任务均为 0。
- 修复真实链路暴露的对象存储分段短读、AI 队列路由/模型配置、SQL 状态类型、Event 绑定与自动证据读取权限，以及 PublicationService 版本字段和 AI judgment 失效权限；每项均增加回归或迁移断言。
- 真实交通运输部 PDF 完成探测、画像、个人受控调度、健康展示、57 页解析、accepted claim、Evidence ID、证据事实和 PublicationService 投影；AI 明确降级且未写事实索引，手工停用后 36 秒抓取数保持不变。
- 使用真实官方字节经生产调度/runtime gateway 执行受控原文变化，旧 claim 立即失效，durable outbox 经 PublicationService 将 Feed/Search 投影撤销；报告明确标注为受控变化，不冒充交通运输部远端自然变化。

### PERS-09 单一个人研究工作区

- `/sources` 收敛为唯一来源入口，统一添加 URL、启停意图、自动发现主题、画像覆盖、自动评分、多采集流健康、熔断自愈、运行摘要与活动历史；旧治理页面导航移除并重定向，不删除历史表。
- Feed、详情、搜索与日报统一标示“证据事实”“AI 判断”“未验证 AI”和“AI 处理失败”；未验证结果保留在统一时间线、搜索和日报独立区块，失败结果不投影模型原始输出。
- 新增来源异常计数和浏览器健康变化通知。通知仅在页面打开、Owner 明确授权且状态变化时发送，以健康 observation 去重，并允许一次恢复通知，正文不含采集正文、Secret、Cookie 或个人敏感信息。
- 保存交互补齐加载、成功、失败原因和重试入口；完成桌面/移动响应式、键盘焦点、状态播报与个人使用指南。

### PERS-08 可撤销的自动关系、事件与型号归一

- 新增 `0028_automatic_relationships`，版本化保存自动关系决定、算法/模型版本、基点分数、理由、输入成员、Owner 纠正与撤销，以及输入变化或事件拆分形成的失效链；所有指向 Item、Document、DocumentVersion、Claim 和 Evidence 的外键均为 `RESTRICT`。
- 内容处理自动建立高置信重复、同一事件、报告后续、型号/版本、主题和相关内容关系。初报、续报和最终调查报告只建立方向明确的后续/调查关系；厂商声明、媒体报道和独立验证保留不同来源角色，不折叠为同一事实来源。
- Event 详情新增 Owner 撤销、拆分、保持独立和型号关系纠正。Owner 决定优先于自动重算；只有成员原文内容哈希或文档版本实质变化后，才允许产生新的关系决定版本。
- 关系变化统一经 `PublicationService` 事务更新 Feed、搜索和日报 generation，并投递缓存/搜索/日报失效事件。旧重复、事件、主题及型号候选表和 API 保留只读兼容，但迁移和 API 双重阻止新增候选。

### PERS-07 AI 判断、未验证 AI 与自动发布闭环

- 新增 `0027_ai_judgment_versions`，版本化保存 Event、文档、证据集合、Prompt/Schema/模型、用量成本、VERIFY 结果、失效原因和投影引用。
- 增加证据事实最小输入的 SUMMARIZE/VERIFY 两阶段处理；DeepSeek 固定使用 `deepseek-v4-flash`、JSON 对象、本地 Schema 校验和至多一次受控修复。
- PublicationService 独占写入 Feed、事实/未验证搜索索引和日报；验证失败但结构合法的结果以独立“未验证 AI”卡片自动发布，处理失败不暴露原始错误文本。
- 文档变化、撤回、纠正和证据失效会在同一事务清除旧投影可达性并重新排队；新增 30 个固定样本的离线评估与 PERS-07 专项门禁。

### PERS-06 证据事实自动接受

- 新增 `0026_automatic_evidence_facts`、版本化自动接受溯源、追加式事实状态、隔离的 `AI_JUDGMENT` 候选及个人内容投影 Outbox；迁移后禁止创建新的 `CLAIM_REVIEW`，历史任务只读保留。
- AI 流水线从抽取直接进入确定性证据门禁；伪造或跨文档 Evidence、数字/金额/日期不一致、缺少企业归因、法律/责任/因果过推、失效证据、冲突和提示注入均不能成为事实。
- DeepSeek 不可用时保留题录、原文链接以及本地规则提取的明确日期、人数和金额；不生成伪摘要。未通过门禁的模型候选只在 Event 详情标为“AI 判断（未验证）”，不进入普通摘要、搜索或日报。
- 唯一 `PublicationService` 消费个人投影任务；文档换版、撤回或替代会事务性失效旧事实和判断、隐藏旧投影并排队重处理。新增 `make personal-content-test`。

### PERS-05 可编辑研究主题、自动发现与自动启用

- 新增 `0025_personal_source_discovery`：7 个固定研究主题、幂等发现记录、上海自然日 100 次探测与 20 次自动启用账本，以及可解释的五项自动评分快照；迁移只为已有来源排队，不联网、不直接启用。
- 每 6 小时优先从已保存的 RSS、Sitemap 和机构页面证据发现一层外链；百度保持独立可选，关闭、缺少 Key 或预算耗尽均不影响免费发现。
- 新增个人来源自动启用事务：总分至少 70 且公网/SSRF、robots、访问障碍、连接器和真实样本门禁均通过时，在每日额度内激活；Owner 手工停用的 sticky 状态始终优先。
- `/sources` 新增自动发现总开关、主题编辑、今日用量、百度状态及来源评分分项解释；个人产品导航不再进入候选审批工作区。旧候选表和 API 仍保留兼容，本轮未实现 Claim 自动接受。

### PERS-04 自动来源画像与轻量纠错

- 新增 `0024_automatic_source_profiles`、不可变画像快照/模型尝试、耐久画像队列和追加式 Owner 覆盖事件；所有已有来源幂等排队重新画像。
- 本地规则从域名、页面、语言/地区、机构线索及 RSS/Sitemap/API/PDF 技术事实生成基础画像；DeepSeek 仅接收同源首页、机构说明和少量栏目摘录，并经提示注入、严格 Schema、Evidence ID 与最多一次 JSON 修复门禁。
- 模型或预算不可用时保留 `PARTIAL` 本地结果且不影响采集；`/sources` 侧栏展示逐字段/总体置信度、证据、理由和版本，区分自动结果与个人覆盖并支持一键撤销。

### PERS-03 来源直接运行、自适应调度与健康自愈

- 新增 `0023_personal_source_runtime`：已启用、探测安全且配置仍为当前版本的 READY 流，可由 PostgreSQL 直接进入个人流调度；旧策略、资格包、试运行和生产审批事实继续保留，但不参与个人流授权。
- 每次物理请求（含重试和重定向）前重新核验手工停用、流配置、允许主机、DNS/IP/peer、限速、预算、超时和重试边界；原始响应继续先写私有对象存储，解析或访问屏障识别失败不会删除证据。
- 新增每流自适应间隔、连续五次失败后 30 分钟熔断、半开探测恢复、连续三次零发现异常与连接器重探测，并在 `/sources` 展示实际运行、中文健康原因、失败次数及自愈/成功/发现时间。

### PERS-02 任意公开 URL 与多采集入口

- 新增 `0022_personal_source_streams`，兼容扩展既有 `source_stream`，并新增耐久 `stream_probe_run` 与 append-only `stream_config_version`。
- Owner 可在 `/sources` 只粘贴一个公开 HTTPS URL；服务端按规范化 Origin 幂等归一来源，以一次性 Worker 探测 RSS/Atom、Sitemap、JSON API、PDF 和公开列表页。
- 探测复用逐跳 DNS/peer 固定、SSRF、robots、重定向、超时、大小和声明式连接器门禁；原始响应先进入私有内容寻址存储，失败不覆盖健康流。本轮不创建长期采集计划。
- 页面增加保存、探测进度、多入口状态/原因和重新探测反馈；新增 `make personal-source-test`。

### PERS-01 个人模式基础与单一 Owner

- 平台唯一产品形态切换为本机单一 Owner 的个人研究模式；旧角色、审批、治理 API 和表仅作过渡兼容，不新增企业模式开关。
- 新增 `0021_personal_source_core`、个人自动化单例设置和不可变来源关键活动事件；Owner 意图、实际运行状态和手工停用优先级分别存储，重复停用保持幂等。
- 新增 Owner-only `/api/v1/sources` 列表、详情和白名单 PATCH，以及响应式 `/sources` 页面；页面明确区分“用户已启用”和“当前正在运行”，未配置来源显示“待自动配置”。
- 保留公网安全、robots、限速、预算、raw-first、证据追溯、Schema 校验和 `PublicationService` 写边界，并明确证据事实与 AI 判断不能混用。

### 来源治理元数据保存反馈

- 修复来源详情“保存治理元数据”在浏览器原生校验失败时没有可见反馈的问题：责任人 ID 格式不正确、必选多选项为空或更新原因缺失时，抽屉内直接显示可操作的校验提示。
- 服务端保存失败现在显示在当前抽屉内；保存成功后关闭抽屉并明确显示“治理元数据保存成功”，同时保留“追加双维评估”作为独立后续操作。
- 页面提示当前登录用户 ID，并说明 Windows 多选方式；不替管理员选择治理分类，也不改变服务端授权和审核门禁。

### 来源中心真实队列查询修复

- 修复来源中心候选、已启用和需处理三条 PostgreSQL 查询：Python 静态检查注释不再被误写入 SQL，所有可空筛选与游标参数均显式指定 PostgreSQL 类型，避免空筛选首次加载返回 500。
- 新增仓储层回归测试，阻止 Python 注释再次污染 SQL，并锁定 asyncpg 可空参数的类型约束；真实 Compose 环境下三个队列接口均恢复为 200。

### R-AI01 AI 配置状态与保存反馈

- `/admin/ai` 新增独立“运行状态”字段，将 DeepSeek 的 `READY` 明确显示为“就绪（READY）”，其他状态明确显示为“未就绪”，不再要求管理员从“运行能力”和“阻断原因”自行推断。
- Secret 保存和配置版本激活新增可关闭的成功/失败提示；请求期间禁用重复提交，只有服务端确认成功后才清空 Secret 输入，失败时保留输入以便重试且不在页面、日志或响应中回显密钥。
- 新增组件和浏览器回归测试，覆盖保存成功后刷新 READY、保存失败保留输入、提示语义及 axe 无障碍检查。

### R-AI01 真实试点端点恢复

- 将 `GOV-003` 试点从运行环境不可达的旧 `zizhan.mot.gov.cn` 附件，收紧到交通运输部政府信息公开站的固定通知附件；只接受精确来源代码和精确 URL，不允许主机通配、重定向扩权或旧地址回退。
- Worker 的 SHADOW 提升继续要求数据库中存在真实 `source_content_outbox=WAITING_AI` 事实；来源合规、连接器、试运行和生产授权仍须由人工治理流程完成，端点恢复不构成自动批准。
- DeepSeek test 环境能力已激活但保持缺少 Secret 时 fail-closed；未配置密钥、预算关闭或来源未获准时不会发起模型请求，也不会生成伪候选。

### R-AI01 单一真实来源 AI 内容准备闭环

- 新增 `0020_ai_content_preparation`：扩展 AI 准备状态机和 `CLAIM_REVIEW`，增加 DeepSeek 固定能力目录、不可变步骤结果、候选 Claim/Evidence 来源、逐条审核决定、来源别名以及 PostgreSQL 权威预算账本。
- 对 `GOV-003` 和唯一获准 PDF 实施精确主机/URL 门禁；通用 Worker 负责 raw-first PDF 解析、最小文本、提示注入扫描、Evidence Anchor、预算与候选物化，隔离 AI Worker 保持无数据库、对象存储、Shell 和工具权限。
- DeepSeek 请求固定为 `deepseek-v4-flash`、`json_object`、禁用 thinking/stream/tools；网络瞬态错误最多重试两次，无效内容最多一次受控修复，每个物理请求调用前预留预算。
- 新增 `/admin/ai` 与 ReviewWorkbench 候选事实视图；候选不会自动接受，不调用摘要、Publication、Feed、检索投影或日报路径。
- 新增 `make ai-content-preparation-test`、`0020` 正反向回放、Mock/安全/预算/Web 测试和无发布副作用检查。真实试点结果以本轮验收记录中的资格门禁结论为准。

### 自动化来源发现、隔离资格审查与单步启用（默认关闭）

- 新增 `0018_source_automation` 和服务端权威候选域：保存候选出现事实、资格运行/隔离捕获/不可变资格包、管理员决定、来源流、激活 Outbox 与搜索供应商月度用量；已有来源只回填为需重新资格审查的默认流，不因迁移自动获得新授权。存在候选、资格包或决定事实时拒绝破坏性降级。
- 新增候选、来源流和需关注队列的 `/api/v1/admin` 契约与后台三工作区。手工 HTTPS 机构地址会自动进入资格审查；`source_admin` 可登记和重审但不能作最终决定，`platform_admin` 的启用/不启用与批量决定要求生产 OIDC 最近5分钟 MFA、幂等键和服务端当前资格包。全绿启用和不启用使用受控审计原因实现一次确认，只有 WARN 启用要求管理员填写具体豁免边界；资格失败且尚无资格包的候选也可被明确标记为不启用。
- 新增版本化资格规则：robots、条款和版权不明确进入 `WARN_WAIVABLE`，登录、验证码、付费墙、非公网地址、越界重定向、无效连接器、零样本/零相关内容及明确阻断进入 `BLOCKED`。WARN 只能逐项记录豁免；BLOCK 永不能启用；材料指纹变化、7天有效期到期或资格包哈希变化均使决定失败。批量启用限同规则、未过期、全绿的1—10项。
- 新增 Celery 资格租约与激活 Outbox。资格运行只处理数据库中的 `qualification_run_id`，原始响应保存在私有 `qualification/sha256` 隔离空间；启用后创建新的 `SCHEDULED + PRODUCTION` 运行并再次直连目标，资格原始证据不会被提升为生产采集结果，重复投递由 PostgreSQL 租约和幂等键收口。
- 新增默认关闭的自动发现任务：每6小时调度代码固定的24个工程行业数字化/安全查询代码，通过钉死的百度千帆 `/v2/ai_search` HTTPS 端点获取最多50项结果，每个查询最多直接核验20个机构域名。供应商查询、标题、摘要和响应保持瞬态；只有通过 DNS/IP/peer 固定、SSRF、重定向、大小、超时和机构域边界的目标站点直连证据才能登记候选。
- 新增 PostgreSQL 原子调用预算：每个 UTC 月前1500次免费，之后每次0.036元；80%阈值只告警一次，200元月度硬上限在供应商 I/O 前停止请求。运行时还会把可配置免费次数、告警阈值和上限钳制为不高于这些产品边界；API key 使用 Secret 配置且不进入任务、响应或日志。
- 复用 Round16 权威调度和健康链路完成自动更新：执行前重读 ACTIVE 来源、当前政策/配置、生产审批、计划、预算和熔断，连续5次失败打开30分钟熔断，连续3次零发现进入异常/需关注队列。新增候选积压、资格请求和候选决定低基数指标；后台对409陈旧资格包只刷新一次，不自动重试决定。
- 通用 `LIST_DETAIL` 不再按 DOM 前50个链接盲截断：先拒绝越界、非 HTTPS、带凭据/查询/片段和重复链接，再按工程/安全/数字化语义、详情路径与导航降权稳定排序；严格配置连接器行为保持不变。该排序提升首批候选内容质量，但不冒充多详情页真实解析验证。
- 新增 `0019_source_content_bridge`：生产 `SCHEDULED + PRODUCTION` 文档的 `READY` 事件原子写入独立内容 Outbox，Worker 仅以 `outbox_id` 幂等创建 `ai_pipeline_run(LIVE, QUEUED)`，失败最多5次并支持只按 ID 重放。交接不会创建 Claim/Evidence、审核任务、Publication 或投影；通用生产 AI 四步编排尚未交付时记录保持 `WAITING_AI`，不能冒充已审核或已发布内容。
- 当前工程默认 `SRBG_SOURCE_DISCOVERY_ENABLED=false`、`SRBG_SOURCE_QUALIFICATION_ENABLED=false`、`SRBG_BAIDU_SEARCH_ENABLED=false` 且无 API key，没有执行真实百度调用或激活任何新来源。资格审核可在关闭付费发现时独立运行，自动发现必须同时开启资格审核；定时自动发现首版仅实现百度通道。Directory/RSS/Sitemap/Outbound Link 仍只是候选渠道契约，自动连接器仅为通用 `LIST_DETAIL` V1，来源流动作写端点和生产告警路由仍需后续收口。本切片不改变第17轮真实试运行 `BLOCKED` 结论。
- 完成0018/0019基线收口复验：一次性真实 PostgreSQL 覆盖0017c→0018→0019升级、窄 Worker 角色、READY 内容幂等交接及两轮受保护降级；Compose 主 Worker 健康检查保留2秒 Celery pong 判定并给予8秒有界容忍。九项根级门禁、Trivy 可交付文件扫描和运行容器默认开关复验通过，未扩大内容桥、来源渠道、AI 编排或发布能力。

### Round 17 扁平授权与真实试运行准备（仍为 BLOCKED）

- 新增仅限 `test` 环境的 `SIGNED_LOCAL_PILOT`：LEO 是唯一超级管理员和批准人；Ed25519 私钥仅保存在被 Git 忽略的根目录 `.env`，服务端验证一次签名并以单事务安装人员绑定、全量20源授权和审计事实。生产环境继续拒绝该模式。
- 新增 `0017c_round17_flat_pilot`，支持签名授权和 `LEO_SINGLE_EXPERT_REFERENCE_SET` 追加式标注；取消 yinzi/baixuejiao 管理职责、双人金标、仲裁和个人绩效阈值，保留匿名聚合容量诊断并明确单专家保证等级更低。
- 窗口启动继续 fail-closed：必须验证签名文档、精确20源、策略/连接器/真实试运行/事件化版本及168小时冻结窗口；客户端、Fixture、候选清单和 `.env` 均不能直接授予来源 `ACTIVE`。
- 修复根目录测试配置污染两个旧生产配置单测；补齐R17导航入口的桌面/移动键盘焦点闭环并更新经人工核对的1024px真实浏览器视觉基线。
- 当前测试库已安装1个LEO签名绑定和1个原子授权；签名安装器自动补录 `NRA-001`，20/20来源均已登记但保持服务端门禁状态。仍有0个ACTIVE、0个当前策略、0个当前连接器配置、0个真实试运行，窗口未启动且LEO单专家参考集为空。`phase2-round17-eval` 与 `golden-replay` 均按设计非零 `BLOCKED`，不得进入第18轮。
- 新增版本化 `round17-flat-evidence-v1` 离线评估入口，绑定签名授权、精确20源、已完成168小时、LEO单专家样本量、直接分项阈值、绝对安全门禁、关键事实当前证据100%、北极星直接计数和经批准测试故障演练；不含双人标注、个人工时KPI或联网抓取。

### Round 17 — 20来源真实试运行与第一阶段金标门禁（工程准备，真实试运行 BLOCKED）

- 新增第17轮 PostgreSQL 权威治理与试运行事实：精确20源窗口、不可变来源段和版本固定、来源变更自动暂停/新段恢复、到期完成检查、真实运行来源隔离、运营计时、人工金标双标/仲裁/冻结，以及由服务端配置钉死的 LEO 唯一 UUIDv7 批准人和受信任 OIDC/MFA 绑定门禁；同名第二主体不能启动窗口、仲裁/冻结或纠正工时。仓库未建立真实人员绑定、未插入事件化通过事实、未批准或激活候选来源。
- 新增统一 `SourceAdapter` 的真实调度运行时，按 raw-first 保存响应并生成 Document；逐跳 SSRF/域名/频率/预算/租约约束在每次物理 HTTP 尝试前重新执行，重试和重定向均计入请求预算。当前来源特定的 accepted Claim/Evidence→Event→PublicationService 链路尚无获准配置，窗口启动因此保持默认拒绝。
- 修复 `SOURCE_FETCH` 重放假成功：失败运行不再转回实时生产调度，而是从哈希一致的既有原始对象进行无网络、`FIXTURE + REPLAY` 诊断回放；执行前再次校验当前策略、连接器和生产审批，回放/Fixture/回填/演练均不能污染真实窗口指标。
- 新增版本化候选20源覆盖矩阵、候选指标/金标定义、真实证据 Schema 和只读离线 eval；evidence 必须由外部 Ed25519 信任锚验证，缺审批、OIDC、168小时窗口、逐源健康、真人金标或真实证据时均非零 `BLOCKED`。候选清单与阈值不构成 LEO 批准事实。
- 新增 `make phase2-round17-test` 与 `make phase2-round17-eval`：前者只运行确定性契约、Fixture、故障、安全、Event/投影和发布旁路测试，可进入普通 CI；后者只读经批准的真实证据与真人金标，不实时抓网，也不提供默认生产公钥。AI观察、付费模型、语义搜索、邮件和企业微信继续关闭。
- 新增 `round-17-20-source-pilot.md` 和机器可读 readiness 记录，逐源诚实标记20个候选均未准入、真实窗口未启动、连续天数为0。由于外部准入、人员身份、真人金标、指标确认和观察证据缺失，本轮结论保持“第17轮未完成/BLOCKED”，不进入第18轮。

### Round 16 — PostgreSQL 权威调度、来源健康与安全重放

- 新增 `0016_scheduling_health_replay`：引入来源计划、分层健康、异常与保留执行事实，扩展 `fetch_run/failed_task/replay_request`；PostgreSQL 以 `FOR UPDATE SKIP LOCKED` 完成并发领取与租约恢复，并在存在 R16 事实时拒绝破坏性降级。迁移兼容修复早期 `failed_task(target_id)` 漂移结构，未验证的 Celery ID 不再被当作业务引用。
- Celery Beat 仅保留一个数据库调度唤醒任务；来源执行消息固定为 `{source_id, run_id}`。Worker 执行租约、重复投递和 Redis 清空恢复均以 PostgreSQL 事实收口，执行前重新校验来源、计划、策略、配置、生产审批、预算和熔断。
- 新增有界指数退避与全抖动、`Retry-After`、熔断开启/半开/恢复、手工暂停优先级，并将传输成功、发现成功、解析质量和业务 freshness 分层；零发现、发布停滞、正文长度突变、必填缺失、DOM 指纹、重复率和队列积压可生成受控异常。
- 失败与重放仅保存权威引用、处理版本、错误分类和幂等边界，旧策略、已删除证据、未知类型和无法重建任务不会恢复丢失 Payload。重放执行限 `platform_admin`，计划管理支持版本、幂等键、step-up 与审计理由。
- 复用现有 OperationsDashboard/来源详情增加计划、健康、异常与重放视图；增加低基数调度延迟、freshness、积压、分类失败、解析质量、熔断、重放、保留与 SLO 指标、Prometheus 告警、Grafana 面板和故障恢复 Runbook。
- 新增 `make phase2-round16-test`，使用隔离 PostgreSQL/MinIO 和实际 Redis/Celery 验证迁移回放、并发领取、重复投递、Redis 丢失重建、安全重放、保留顺序、观测和管理页面。该证据不代表真实来源连续运行或生产告警路由。

### Round 15 — 来源中心 V2 与声明式连接器契约

- 新增服务端权威的 `CANDIDATE → COMPLIANCE_REVIEW → TRIAL → ACTIVE → PAUSED → RETIRED` 生命周期、治理责任人、五维覆盖属性、合规策略版本、职责分离审批、Fixture/真实试运行隔离、状态事件和可回滚的 Alembic 兼容迁移；旧 `FIXTURE_TEST`、`APPROVED`、`ACTIVE` 与 `enabled` 均保留迁移证据，任何旧行都不会自动获得 V2 生产授权。来源权威/独立性评估时间必须携带时区并归一为 UTC，迁移后任一治理元数据或权威引用变化都会阻止破坏性数据库降级。
- 新增六类版本化声明式连接器定义与严格 JSON Schema：RSS/Atom、JSON API、Sitemap、列表/详情、PDF、人工 URL/文件导入；禁止脚本、模板表达式、动态目标与配置内明文凭据，V1 固定目标及逐跳重定向拒绝全部 URL query、API 分页固定为 `NONE`，纯预览只校验和脱敏、不写审计且不执行网络 I/O，凭据仅保存受控密钥系统引用。
- 新增六类固定样本回放的统一 `DiscoveryRecord → FetchResult → RawObject → DocumentVersion` raw-first 契约，以及逐跳 DNS/IP/重定向校验、连接 IP 固定、DNS/连接/读取/对象存储超时、封顶重试退避/限速/User-Agent、跨源凭据重定向拒绝、上传聚合预算/MIME/压缩炸弹/嵌套危险 PDF/主动内容防护；固定回放不冒充真实联网执行，Fixture 永不形成生产审批证据。
- 新增复用 AppShell 的来源列表、详情、策略、连接器配置、试运行、审批/暂停/退役、审计和五维覆盖缺口后台，以及来源治理指标、告警、Runbook 和 `make phase2-round15-test`。`ACTIVE` 仅是服务端权威生产 eligibility；本轮未交付生产执行器或动态数据库调度，旧 MEM 调度固定返回零任务并记录受控阻断指标。真实来源联网与正式试运行均为 0，未批准任何具体来源，也未激活具体来源；46 条种子保持 `CANDIDATE/enabled=false`。
- 收口全站回归时保持 Round14 Event 详情单端点：类型详情按 tagged `type_detail` 安全渲染，安全案例证据抽屉只展示 Event 发布投影已有的定位、哈希与关联 claim；来源后台导航按服务端身份角色收敛，并以固定身份重建三张桌面视觉基线，未用 CSS 或快照阈值掩盖权限变化。
- 独立验收以失败测试补齐来源登记、策略、配置、试运行、生命周期、覆盖缺口和调度阻断的字段白名单结构化日志，强化来源健康告警、仪表盘与可操作 Runbook；URL、配置正文、凭据引用、Cookie 和原始响应不会进入日志。配置回滚只追加新版本，保留全部历史事实。
- 独立验收发现已记录开发版 `0015_source_center_v2` 的本地数据库存在同 revision 结构漂移；新增数据保留型 `0015b_source_center_convergence` 收敛迁移，事务内补齐 Fixture replay 表、Document kind、写入边界、执行域触发器和角色权限，并验证既有治理事件不丢失。除 API 的受控配置投影外，runtime/worker/publisher/model 均不能读取 `credential_ref`；伪造 `PRODUCTION` 文档版本由数据库默认拒绝。

### Round 14 — Event 统一身份、关系拆分与 Item 兼容迁移

- 完成独立验收指出的收口项：`published_v1` 升级为 1.1.0 Event 修订投影，默认普通 Feed/Event/搜索/已发布日报/收藏读取装配到 `srbg_projection_reader_login`；搜索投影、日报快照、收藏、专题和反馈的新事实均携带或仅写入 `event_id`，Event 详情页由单一接口返回 claims、evidence、documents、来源对比与类型详情。新增 `0014b_event_consumer_switch` 的 `SHADOW/EVENT/ROLLBACK_READ_ONLY` 权威开关和只读回滚保护，并以非空 TEST PostgreSQL 数据对旧收藏、专题、日报、反馈、搜索、publication revision、event revision 与 R3 ACL 完成 1:1 对账。
- 独立验收修复了应用回退到 0013 时读取 0014 Event 列及 alias 权限导致的失败，并补齐五类身份迁移告警和 Runbook。复验同时确认本轮仍未完成：默认普通读取装配和多个 consumer 查询仍走业务表/`item_id`，与专用 `published_v1` 和单次 Event consumer switch 约束不符；README 与验收结论已改为 `NOT_COMPLETED`，没有以现有绿测掩盖该架构差异。
- 扩展现有 Event 为显式通用事件模型，增加稳定 canonical identity、版本、合并/拆分/回滚工作流和不可变 Item alias；没有创建平行事件服务或 `PROVISIONAL_EVENT`。
- 分离 Document 来源角色、Event 生命周期、Event-Entity、Topic-Event 和受控分类关系；八类 Item 显式映射 Event 类型，模糊匹配只生成候选且 `auto_merge` 保持关闭。
- 以版本化、幂等、可断点恢复任务完成 shadow backfill 和 consumer parity；已发布 Item 身份 23/23 可解析，差异为 0，23 条未知来源角色进入人工队列。
- Feed、搜索、日报、收藏、专题、下载和详情在一次 consumer switch 中改用 Event；旧 Item 页面只返回 308，读取 API 返回 `Deprecation/Link` 和可配置 `Sunset`，旧写接口返回 410。
- 合并、拆分和回滚经 reviewer、`PublicationService` 与追加式审计执行；新增 Round14 专项门禁、真实 PostgreSQL 引用完整性测试、兼容 E2E、R3/R4 越权测试和迁移/别名/候选/回滚指标。

### Round 13 — 内部发布投影、Event 身份与权限隔离

- 新增 Alembic `0013_internal_projection` 和版本化 `published_v1` schema，以稳定 Event 公开 ID 保存 `PublishedEventSummaryV1`/`PublishedEventDetailV1` 影子投影、字段来源、generation、publication revision、生成时间、失效原因和审计引用；既有 `publication_projection_state` 继续只负责搜索、缓存与日报失效。
- 拆分并约束 `publication_risk_tier`、`content_severity`、`projection_level`，保留旧 `risk_level` 的精确兼容映射和可回滚路径；R3 待审核仅生成官方题录 `METADATA_ONLY`，服务端排除精选、日报、推荐、通知和全文导出，R4 始终零投影。
- 新增 PublicationService writer 边界内的幂等影子回填与对账：本地验收数据形成 32 个稳定 Event、23 条 `FULL`、9 条 `METADATA_ONLY`，连续两代 source/projected 均为 32、差异为 0；未切换现有 Feed、搜索、日报、收藏、专题或详情消费者。
- 新增真实 PostgreSQL 低权限 `srbg_projection_reader` 登录验证，只能读取版本化发布视图，不能获得业务 schema/table、原始对象、审核备注、审计表、R4 数据或投影基表的 `USAGE/SELECT`；查询、游标、旧 generation、搜索和导出绕过均有负向测试。
- 收紧 OIDC/RBAC：非开发环境拒绝本地身份头，验证 issuer/audience/RS256/kid/exp/nbf/iat/角色和 JWKS 默认拒绝；来源启停与发布职责分离，高权限写操作要求短时 MFA step-up，CORS 使用精确 allowlist，Nuxt 代理不转发客户端伪造身份头。
- 撤销运行角色对 `audit_log` 的直接写权限，通过受控数据库函数计算链值，并把链根锚定至独立对象存储；该能力仅称 append-only/tamper-evident，不宣称对数据库管理员绝对不可篡改。
- 新增投影生成/失效、权限拒绝、R3 降级和对账差异的结构化日志及低基数指标，新增 `make phase2-round13-test`、迁移正反向回放、发布路径审计、Web E2E/a11y 无破坏回归，并更新 README 与本轮验收记录。
- 独立复验修复回填 CLI 绕过 `PublicationService`、accepted claim 字符串二次 JSON 编码、运行时投影/锚定健康指标缺失和审计锚定未定期调度的问题；新增 PostgreSQL 权威指标、每日锚定、Prometheus 差异/陈旧告警、fail-closed Runbook，以及真实 reader/runtime 权限与结构化拒绝日志负向测试。

### Round 12 — 真实能力审计与二阶段基线

- 新增 `docs/audit/phase-2/` 十二项只读审计产物，以代码、实际数据库登录、运行API、测试和外部证据重新分类来源、连接器、Event/Item、发布投影、R3/R4、审计日志、用户行为、模型、指标和150来源风险；没有把CHANGELOG或方案声明当作实现证据。
- 确认46条种子均为CANDIDATE，运行库54条ACTIVE全是固定/集成测试来源，108次采集全为FIXTURE；因此真实端到端追踪为`NOT_AVAILABLE`，生产模型、通知、国际来源、连续运行和真人金标指标均保持null。
- 实测API/Worker登录可读写大量业务表和audit_log，普通用户尚无专用只读发布投影；audit_log可由运行角色自造INSERT、仅UPDATE/DELETE受不可变触发器阻止，且无独立hash根锚定。Event/Topic运行数据为空，门户、发布、搜索、日报和收藏仍以Item为身份。
- 全局quality gate、Round08—11、42项E2E和13项a11y通过；Round02—04旧专项因隔离迁移边界缺少`ai_pipeline_run`失败，smoke因旧版本响应断言失败，严格真人金标/readiness按设计BLOCKED。本轮未修改业务代码或测试阈值，结论保持未完成。
- 独立验收以失败测试复现并修复上述工程漂移：隔离集成默认回放当前0012 head，smoke校验完整版本契约并按权威Feed区分空态/有数据状态；同时修复未评分已发布内容进入`/selected`的回归。Round01—11专项、quality gate、fixture replay、smoke、42项E2E和13项a11y现均通过；严格真人金标/readiness仍因五类真实样本为0保持BLOCKED。

### 二阶段文档基线

- 固化企业内部 OIDC/SSO、Event 唯一用户身份、R3 `METADATA_ONLY`、Item 只读兼容、确定性归并和专用只读发布投影等已确认决策，删除匿名公开、`PROVISIONAL_EVENT`、R0、1000 候选硬指标和 `source_trust_score` 等冲突要求。
- 将执行顺序统一为 11F、11P、12—21，并按 20→50→100→150 来源门禁安排 AI、外部通知和国际来源；明确第 11 轮工程切片 `PASSED` 与生产证据 `BLOCKED` 是不同状态，第 12 轮无获准 ACTIVE 来源时真实追踪记录 `NOT_AVAILABLE`。
- 更新 README 的现状与文档导航；本次仅固化文档，不修改业务代码、数据库、依赖、配置、测试阈值或运行环境。

### Round 11 — 质量、运维、安全与上线门禁

- 新增 PostgreSQL 权威的最小失败任务、优先级人工重放、不可回溯个人的聚合运行指标和显式反馈；失败记录不保存正文、令牌、Cookie、模型输入、个人敏感 Payload 或关联哈希，解析/AI 重放在无法安全重建时默认失败。复用唯一 `PublicationService` 及既有 Feed/卡片/AppShell，交付来源健康、运行中心和质量看板。
- 接入固定版本 Prometheus/Grafana/Alertmanager/OpenTelemetry 与 Sentry 配置，增加来源、队列、解析、AI、审核、API、搜索、成本、SLO/错误预算和备份验证告警基线。
- 新增隔离恢复演练、负载/成本基线、环境隔离、发布/回滚/撤回/来源故障/模型异常/Redis 重建 Runbook，以及 OIDC RS256/JWKS、依赖/密钥/配置和发布对抗门禁。
- 新增版本化金标目录、readiness Schema/评测器和 CI required checks；工程 CI 成功校验 Schema、引用完整性及诚实 `BLOCKED`，严格 golden/readiness 保持非零晋级门禁。证据主体区分 AGENT/CI/HUMAN，证据包记录空金标、短实测窗口和未配置生产路由，生产状态保持 `BLOCKED`。

### Round 10 — 信息流、搜索、专题与日报

- 在既有 `/api/v1/feed?mode=selected|all`、`/items/{id}`、`/events/{id}` 和 `/hot-topics` 上统一补齐签名 Cursor 分页、组合筛选、ACL 投影和稳定 ETag/304；新增 `/search`、`/daily`、`/reports/{id}`、`/fingerprint`、`/saved-items` 与私有专题接口，没有创建平行 `/items` 或 `/events` 列表。
- 新增 Alembic `0011_feed_search_daily` 与 PostgreSQL 17.10 + pg_trgm/pgvector 基础：编号、文号、标准号和 DOI 规范化精确匹配永远排在标题/实体/标签 trigram、中文正文 bigram FTS 与可选语义召回之前；语义能力默认关闭、超时可降级，不能压过精确编号结果。
- 收藏和自定义专题按用户隔离并在读取时重新应用当前 ACL；写入支持 Idempotency-Key，专题修改使用 If-Match。R3 仍只返回服务端白名单投影，R4 和管理内容不进入普通用户响应。
- 日报草稿以固定 publication revision 快照生成，只能由 reviewer 审核后经唯一 `PublicationService` 发布；已发布日报保持历史标题和顺序，当前撤回状态以文字覆盖且不泄露旧摘要。新增 Markdown 导出，并对可能触发表格公式的前导字符执行转义。
- 扩展既有发布投影 Worker，使发布、修订和撤回同步维护搜索与日报 generation/visible 状态；详情继续复用 accepted claim、事实清单、证据抽屉、来源冲突与版本时间线，原文失效、来源延迟、撤回和无 AI 均有显式降级状态。
- 复用 `AppShell`、`IntelligenceFeedPage`、`TimelineFeed`、`IntelligenceCard` 和冻结的 `FeedPage`/`ItemSummary`，新增搜索、日报、收藏页面并完善首页、精选、全部、数字化和安全频道；首页首屏展示今日重点、数据更新时间和异常提示，不使用装饰 Hero。
- 搜索与收藏页面通过共享 Feed 的加载更多契约追加 Cursor 页；首页视觉基线覆盖 1920×1080、1440×900、1024×768、768×1024，安全/撤回状态均同时使用文字，768 阅读宽度和 200% 等效视口保持可操作。
- 新增迁移回放、搜索排序/游标/ETag/ACL、日报快照/发布、收藏专题、投影 Worker、性能 SLO、Playwright 关键路径和 axe 测试；部署实测搜索 40 次 P95 31.05 ms，低于 800 ms 门槛。

### Round 09 — 受控模型网关、审核治理与发布版本

- 新增无工具能力的受控模型网关、确定性 Mock provider 和可配置 OpenAI 兼容 provider；分类、事实抽取、摘要、发布前复核四步均绑定不可变 Prompt、JSON Schema、模型参数、输入 SHA-256、原始/校验后输出、Token、微美元成本和耗时。
- 新增 Alembic `0010_ai_editorial_governance`，保存 AI 运行、Prompt/Schema/模型版本、注入扫描、安全决定、内容审核决定、历史回放、影子结果、质量报告及发布投影状态；AI Worker 使用独立队列且没有数据库、对象存储、Shell 或工具权限。
- 将唯一 `publication_gate.json` 升级为 `2.1.0`，由唯一 `PublicationService` 现查来源、当前文档、证据、审核、风险和安全事实；模型自报的来源等级、审核状态、风险、安全处置和发布建议均不能授权发布，R3/R4、事故原因/责任和法规效力保持强制人审。
- 扩展原有发布服务完成批准、拒绝、纠错、修订、撤回和重发的不可变 `review_decision`/`publication_revision` 工作流；API、后台动作、Worker 和脚本的发布路径审计确认不存在平行入口，应用层与 PostgreSQL 最小权限共同阻止直写发布表。
- 发布、修订和撤回在同一事务推进搜索、缓存和日报投影 generation；publisher worker 经 `PublicationService` 消费投影事件并原子更新 Redis generation/visible 指针，撤回后旧缓存版本不可达，已发布修订快照不被模型升级静默改写。
- 复用 `AppShell`、`IntelligenceFeedPage`、`TimelineFeed`、`IntelligenceCard`、冻结的 `FeedPage`/`ItemSummary`、`PdfEvidenceViewer`、`FactList`、`EvidenceDrawer` 和 `StatusBadge`，新增三栏 `ReviewWorkbench`，并在信息流/详情增量展示 AI 辅助、Prompt/Schema/模型版本、无 AI 降级、修订和撤回状态；完整摘要只允许引用 accepted claims。
- 新增恶意固定样本、模型输出对抗、发布绕过审计、迁移/RBAC、fixture replay 和质量报告；覆盖忽略指令/密钥泄露、额外字段、错误 JSON、伪造 evidence_id、无证据事实、企业声明缺归因以及伪造审核/权威/安全处置。

### Round 08 — 去重、事件聚类、热点和评分

- 新增 Alembic `0009_dedup_events_scoring`，统一保存 URL/外部 ID/DOI/机构域内文号/哈希身份键、正文指纹、重复候选与决定、来源谱系、主题聚类、八维评分、人工覆盖和回归样本；决定与审计均为追加式，运行角色不能直接写人工决定。
- 实现规则候选召回和可选 pgvector 召回的并集，最终合并始终先执行项目、标段、型号、文号和事故阶段硬约束；修订、澄清、撤回、更正及后续材料形成关系，不按重复删除，生产自动合并固定关闭。
- 识别转载链和同机构镜像并按独立来源主体计数；将事件扩展到安全事故、法规变化、数字化项目、研究成果和产品发布，新增事件/主题/关系人工工作台，所有决定必须填写理由并经唯一 `PublicationService` 写审计和回归样本。
- 新增相关性、权威、影响、新颖、时效、证据、置信和热度八个独立分项，保存特征解释、规则版本、原始分和人工覆盖理由；热度不参与置信分计算，普通卡片最多显示一个明确命名的“相关度”入口。
- 复用 `AppShell`、`IntelligenceFeedPage`、`TimelineFeed`、`IntelligenceCard`、`FeedPage`/`ItemSummary`，新增 `/hot`、事件来源对比和 `/admin/clusters`；同一通稿转载不会增加热点独立信源数。
- 新增 300 对重复/非重复与 100 事件的首版内部固定金标结构、离线精确率/召回率/聚类纯度评测、迁移/RBAC/契约/API/E2E/axe 测试和 `make round08-test`/`make round08-eval`。样本尚未人工裁定，结果明确标记为内测评估，不能据此开放自动合并。

### Round 07 — 软件、物联网、低空和 AI 设备

- 新增 Alembic `0008_technology_products`，以统一 vendor/product/model/version/profile/capability/taxonomy 模型表达四类技术产品；型号和版本分别保持唯一身份与历史记录，同名不同型号不静默合并，疑似别名、后继版本和重复项进入人工归一候选。
- 将厂商声明与独立验证能力在数据库约束、契约、publication gate `7.0.0`、统一 API、共享卡片和详情页全链路分离；已验证能力必须携带独立证据，任何产品内容不得生成“四川路桥采购”结论。
- 复用既有来源准入和统一 `SourceAdapter`，提供广联达软件与大疆低空设备的最小固定回放；ENT-007/008 继续保持 `CANDIDATE/disabled`，固定样本不授予生产采集资格，厂商图片默认不下载。
- 增量扩展冻结的 `FeedPage`、`ItemSummary`、`TypeSummary` 与详情契约，在同一 `/api/v1/feed`、`/api/v1/items/{id}`、`/digital` 和 `IntelligenceCard` 支持 SOFTWARE_PRODUCT、IOT_PRODUCT、LOW_ALTITUDE_EQUIPMENT、AI_EQUIPMENT 及产品类型、证据等级、部署方式、场景和成熟度筛选。
- 产品详情统一显示“产品能力/工程证据/许可与限制”，通过经审核的 `APPLIED_IN` 关系连接数字化案例；低空设备固定提示“产品发布不代表空域、适航、飞手和项目许可。”，无官方许可证据时许可状态为 `UNKNOWN`。
- 在既有审核工作台增加 reviewer 专用型号/版本归一入口，所有决定只经唯一 `PublicationService` 写入并追加审计；新增按类型/证据/许可、能力分组及待归一队列指标，以及契约、迁移回放、门禁、固定回放、E2E 和 axe 测试与 `make product-test`。

### Round 06 — 期刊论文

- 新增 Alembic `0007_papers`，以论文题录、作者/机构、来源记录、受控分类、候选去重和经审核的更正/撤稿关系表达学术元数据；DOI 使用规范化唯一索引，无 DOI 时以规范题名、首位作者和年份生成候选指纹，并完成 `0006 → 0007 → 0006 → 0007` 隔离回放。
- 接入统一 `SourceAdapter` 下的 OpenAlex 游标分页连接器与 Crossref DOI/更新关系补充器；共享 HTTP 客户端统一执行域名白名单、超时、限速、礼貌 User-Agent、条件请求、有限重试、熔断和 `Retry-After`，固定响应不授予生产来源 active 权限。
- publication gate 升级至 `6.0.0`，由唯一 `PublicationService` 校验论文身份、accepted claim、研究成熟度、访问许可和更正/撤稿关系；运行角色不能直接写正式关系，未授权全文永不落入对象存储或浏览器响应，摘要许可不清时仅投影题录和原文链接。
- 增量扩展冻结的 `FeedPage`、`ItemSummary`、`TypeSummary` 与详情契约，提供 DOI、期刊、ISSN、作者、机构、卷期、年份、关键词、开放状态、论文类型、工程专业、技术标签、研究成熟度、相似论文、RIS/BibTeX/GB/T 7714 引用及原文入口。
- 复用 `AppShell`、`IntelligenceFeedPage`、`TimelineFeed` 和 `IntelligenceCard`，在既有 `/digital` 增加论文 Tab、筛选、共享卡片和详情；元数据、摘要、全文权限分区显示，撤稿/更正显著提示，并明确“研究结果不代表已完成工程生产应用”。
- 新增 OpenAlex/Crossref/中国公路学报固定样本、API Mock、版权边界、迁移/契约/门禁/固定回放/E2E/axe 测试和 `make paper-test` 专项门禁；知网、万方维持授权 API 或人工题录方式，禁止绕过登录或付费机制。

### Round 05 — 数字化转型案例

- 新增 Alembic `0006_digital_cases`，以数字案例档案、受控分类、企业/技术/项目实体关系、claimed/verified 成效和 `relevance-v1.0.0` 分项事实表达数字化案例；空库支持 0005→0006→0005→0006 回放，存在数字案例数据时拒绝破坏性降级。
- 接入交通运输部政府案例汇编与蜀道集团企业案例两个统一 `SourceAdapter`，Git 仅固定短摘录、原文 URL、PDF 页码和 SHA-256；生产来源保持 `CANDIDATE/disabled`，不能由样本自报 active。
- publication gate 升级到 `5.0.0`；分类、成熟度、归因、独立证据、允许动作和相关性规则均由服务端权威上下文默认拒绝校验，企业自述未经职责分离的人工审核不能进入精选。
- 扩展唯一 `PublicationService` 的审核事务，支持修改工程专业、生命周期、技术、场景、成熟度和成效归因；修改只能选择当前版本 accepted claim 和已有独立证据，随后由服务端重算相关性。
- 复用 `AppShell`、`IntelligenceFeedPage`、`TimelineFeed`、`IntelligenceCard`、`FeedPage`、`ItemSummary` 和证据抽屉完成 `/digital`、筛选、全部/精选、卡片、详情和审核页；不创建数字化专用卡片或平行查询/发布实现。
- 明确分列“发布方声称的成效”和“独立证据支持的成效”，所有量化结果可回到证据；卡片显示政府/行业案例源或企业自述、厂商声明、成熟度、场景、部署规模、四川路桥关系及可解释相关性，不显示为可信度。
- 新增数字案例量、来源/成熟度、claimed/verified 成效和企业待审核队列指标，以及契约、规则、迁移、固定回放、PublicationService、E2E、axe 和 1440×900 新页面截图。

### Round 04 — 安全案例生命周期

- 新增 Alembic `0005_safety_case_lifecycle`，以 `safety_case_profile`、事件、事件材料候选/决定/成员、关系候选/决定/正式关系、逐字段审核、事实冲突及追加式审计表达初报、续报、正式调查、处罚、整改、更正与撤回；迁移提供实验室降级/再升级验证，生产回滚保留事实表。
- 将日期、地区、项目、主体和事故类型五维匹配接入生产候选服务；分值与维度版本化落库且只能进入人工审核，不会自动写 `event_item`，同一事故不同阶段始终保留为独立材料并建立后续关系。
- 为伤亡、损失、正式原因和责任实施逐字段证据门禁：伤亡/损失仅接受 A0/A1 一手官方证据，原因/责任还必须来自正式调查或处罚阶段；审核决定不可逆、提交人与审核人分离，未关联事件或证据不足时默认拒绝。
- 新增冲突检测与工作台；新冲突立即把普通投影降级为“待核实”，不返回候选值、Claim ID 或证据定位，历史已接受值只保留在受控审计中；更正、撤回和后续关系均记录审核人、理由与哈希链审计。
- 冲突决定同时覆盖 `KEEP_CURRENT` 与 `ACCEPT_CANDIDATE`：落选 Claim 不再进入发布门禁、后续冲突基线或普通详情，撤回材料的事实不再参与事件头部聚合，后续有效正式材料可替代较早事实而不改写历史。
- publication gate 升级到 `4.0.0`，逐字段验证所有公开安全案例元数据均来自同一材料的 accepted claim 和有效定位证据；R4/未发布材料不能影响公开事件标题、身份、状态或关系投影，运行时角色只能读取去标识的冲突安全投影。
- 复用唯一 `PublicationService`、`FeedPage`/`ItemSummary`、`AppShell`、`IntelligenceFeedPage`、`TimelineFeed` 和 `IntelligenceCard`；在同一 `/safety` 增加规定/案例筛选及 `SafetyCaseTypeSummary`，新增事件时间线、已确认事实、待核实事实、受控标签和已审核关系/更正记录，没有平行信息流或发布链路。
- 新增固定的梅大高速“5·1”塌方灾害官方初报、续报、调查报告、追责通报和整改评估样本，锁定来源、原始 URL、SHA-256、阶段与关系；端到端演示完整五阶段证据、伤亡冲突处置、调查中状态、正式结论、撤回和更正审计。
- `/metrics` 改为仅 `PLATFORM_ADMIN`/`AUDITOR` 可访问，匿名健康与就绪探针保持不变；新增事件候选、待处理冲突、调查中案例、未结整改、关系审核及 publication gate 拒绝原因指标与结构化日志。
- Web 运行镜像改为构建阶段生成 Nuxt/Nitro 产物、运行阶段只启动预构建服务，消除开发服务器冷转换导致的首次审核页超时；首次冷启动 Playwright 保持零重试、原超时和全部断言通过。

### Round 03 — PDF、OCR 与版本变化

- 修复 Round03 基线复验发现的时间线语义：初次采集以首次发现时间作为 `activity_at`，保留独立原文发布时间；仅元数据版本不推进活动时间，实质版本以同一服务端时间推进 `activity_at/updated_at`；Feed 游标解码为数据库驱动原生 `datetime/UUID`，并以真实 PostgreSQL 锁定同活动时间的稳定 keyset 分页。
- 将 `make pdf-ocr-test` 与 `make safety-regulation-test` 改为每次创建唯一临时 PostgreSQL 数据库、私有 MinIO 桶和临时最小权限登录角色；迁移和测试不再写共享业务库或重置固定角色密码，异常、碰撞与中断路径均执行所有权感知清理，默认拒绝非回环集成端点。
- 将本地 Playwright 与 CI 统一为 2 workers，消除 Compose `nuxt dev` 在 4 workers 并发 SSR 导航下偶发的根文档无响应；保留 29 个 E2E、原超时、零本地重试和全部视觉/行为断言。
- 扩展统一 `SourceAdapter`、私有文档库和 Alembic `0004_pdf_ocr_versioning`：新增原始对象安全事实、文档版本状态事件、附件树、PDF 页面/文本块/表格单元格、版本变化、关系/法规状态候选与决定、内容生命周期、确定性摘要和事务性 Outbox；失败或隔离版本不会替换既有 `READY` 当前版本。
- 新增有界 PDF 安全检查和一层 ZIP 解包，拒绝 MIME 不符、加密、JavaScript/OpenAction/Launch/自动外链、内嵌文件、路径穿越、符号链接、嵌套归档、规范化重名和预算超限；parser 与 publisher 使用独立低并发队列和数据库角色，只有唯一 `PublicationService` 可形成发布、撤回或关系/法规状态决定。
- 新增 PyMuPDF 原生文本/表格提取与本地 Tesseract `chi_sim+eng` OCR 适配器，持久化 1 起始页码、旋转归一的千分之一 point 坐标、阅读顺序、词级置信度和页面预览；文本、语义正文、元数据与原始字节分别计算 SHA-256。
- 新增确定性变化检测和重锚：重复页眉/页脚及元数据变化归为 `METADATA_ONLY`，正文、文号、实施日期、数字/效力词/否定词等硬规则变化进入 `CONTENT_UPDATE`；实质变化通过 Outbox 使旧 Claim、摘要和发布修订进入 `UPDATE_DETECTED/RE_REVIEW_PENDING`，普通投影立即降级。
- 保持 `FeedPage`/`ItemSummary` 兼容，只增量加入文档状态和版本提示；复用 `AppShell`、`IntelligenceFeedPage`、`TimelineFeed`、`IntelligenceCard`、`EvidenceDrawer`，组合 `PdfEvidenceViewer`、`VersionTimeline` 和 `DiffView`，支持页码跳转、坐标高亮、键盘焦点归还、撤回最小投影和四断点视觉回归。
- 新增版本时间线、页级预览、按页差异、候选审核和仅升级为实质变化的 `/api/v1` 契约；publication gate 升级到 `3.0.0`，现查 `READY`、安全状态、服务端哈希、当前证据、OCR 关键字段置信度、来源准入、职责分离及关系/法规状态决定。
- 新增测试专用 PDF/OCR/表格/恶意动作/错误 MIME/超大页/附件与压缩炸弹黄金样本、真实 PostgreSQL/MinIO/ClamAV/Redis/Tesseract/parser/publisher 纵向集成门禁 `make pdf-ocr-test`，以及 PDF 解析率、OCR 可用率、低置信关键字段、版本变化和 Outbox 指标。

### Round 02 — 首个安全规定 HTML 来源

- 以应急管理部 `GOV-006` 为唯一生产连接器，新增统一 `SourceAdapter`（兼容别名 `SourceConnector`）、`DocumentParser`、固定官方 HTML 回放样本、条件请求、重试、限速、持久化熔断、幂等和 SSRF 默认拒绝防护；生产连接器保持 `CANDIDATE/disabled`，测试来源必须经真实 30 样本准入服务激活。
- 新增安全规定采集、处理、字段证据、R3 审核、发布与不可变修订迁移；原始响应先进入私有文档库，文号、机关和发布日期由规则解析并绑定 `html-p-NNNN` 段落定位，法规状态默认 `UNKNOWN`。
- 新增唯一服务端 `PublicationService`，以 `publication_gate.json` v2 和服务端现查事实执行默认拒绝门禁；普通发布允许缺省评分，未评分内容禁止进入 `/selected`，候选自报授权字段无效。
- 新增专用数据库发布角色；API、Worker、管理员和模型角色仅可读取发布表，绕过服务的直接写入由 PostgreSQL 权限拒绝。R3 提交人与审核人强制职责分离，审批、发布、修订、撤回和重发均经统一服务与哈希链审计。
- 冻结 `FeedPage`、`ItemSummary`、`FeedNotice`、`TypeSummary` v1，完成服务端 R3 白名单投影以及 `/selected`、`/all`、`/safety`、最小详情和审核工作台；复用 `AppShell`、`IntelligenceFeedPage`，仅新增一套 `TimelineFeed`、`IntelligenceCard`、`EvidenceDrawer`、`FilterPanel`。
- 新增解析黄金、连接器安全、固定回放、集成、RBAC、契约、E2E 与 axe 测试；修复 BFF 丢失 Feed 查询串和客户端 Feed hydration mismatch，保证无真实评分时精选为空且浏览器永远收不到 R3 受限字段。

### Round 01 — 来源注册与原始文档库

- 新增来源、准入策略、连接器、不可变原始对象、文档版本、附件与哈希链审计日志迁移，并将 42 个种子来源以 `CANDIDATE/disabled` 导入；
- 新增服务端来源状态机、证据重算和默认拒绝门禁，数据库字段、CSV 或请求参数均不能直接形成有效 `ACTIVE`；
- 新增 HTML/PDF 人工样本上传、MIME/大小/文件名/PDF 主动内容/杀毒校验、SHA-256 内容寻址与跨文档去重，并以摘要固定官方 ClamAV 1.5.2 镜像作为 Compose 私网健康依赖；
- 新增来源准入 API 与复用 `AppShell`、`PageHeader`、`StatusBadge`、`ResponsiveDrawer` 的管理端来源和文档元数据页面；
- 新增单元、契约、权限、真实 PostgreSQL/MinIO 集成、Playwright 与 axe 测试，以及 `make source-fixture-test`。

### Round 00A — 方案1设计系统与应用壳层

- 以 `design_tokens.json` 为单一视觉权威，建立类型安全的 `@srbg/ui`、Tailwind 与 Nuxt UI 主题映射；
- 为 Nuxt 4 接入统一应用壳层、共享 `IntelligenceFeedPage`、频道导航和真实 API/Schema 工程状态与空态；页面头以可访问的 `time` 显示实际版本检查时间，并统一承载状态；
- 完成响应式侧栏/抽屉、键盘与焦点管理、reduced-motion、axe 和四断点视觉回归，并修复 UUIDv7 请求标识、SPA 导航及当前导航的路径边界匹配；
- 将运行时烟测同步到“四川路桥 / 智安情报”文字锁定稿与真实业务空态；
- 本轮未修改后端、业务 API 或数据库迁移。

### Round 00 — 工程基线

- 建立 `apps/web`、`apps/api`、`apps/worker`、`packages/contracts`、`infra` monorepo；
- 增加 FastAPI 健康、readiness、版本与 Problem Details 契约；
- 增加 Celery Worker 健康任务和可正向执行的 Alembic 基线；
- 增加采用设计令牌的演示首页、组件测试、Playwright E2E 与 axe 无障碍测试；
- 增加 PostgreSQL、Redis、MinIO、迁移、API、Worker、Web 的固定版本 Compose 栈；
- 增加 Ruff、mypy strict、pytest、ESLint、TypeScript、Vitest、契约与安全门禁；
- 增加 GitHub Actions CI、运行时冒烟、Redis 降级恢复验收；
- 将项目工具和缓存限定在 D 盘，并验证 Docker 数据位于 `D:\Dockerdata`；
- 修复 Compose v5 项目目录、宿主端口覆盖、Nuxt CSP 水合和多版本 esbuild 回退问题；
- 修复 Windows Make 子进程无法发现 D 盘 Node 的问题，并排除运行镜像中的仓库说明与测试材料；
- 浏览器门禁复用健康运行栈，避免重复强制构建受外部镜像仓库短时故障影响；
- 增加基于 Git 可交付文件清单的确定性 Trivy 扫描，避免本地 Junction、工具和缓存污染安全门禁。
# Unreleased

- PERS-10：新增 `0029_legacy_governance_retirement`，以逐行/分类 SHA-256 和数量校验归档并退出旧企业治理；降级可校验后重建旧结构、授权和数据。
- 产品只保留固定本地 Owner；删除旧管理 API、角色分支、页面、组件及资格审批/Operations 后台任务，AI 配置迁移到个人设置。
- 新增 `personal-migration-test`、30+30 固定样本最终评估、迁移/回滚/备份文档和真实验收记录。
## 2026-07-22 (Issue #41 autonomous content production switch)

- Connected the versioned autonomous qualification policy to the real content Worker. Locked negatives filter before model dispatch; other candidates use the strict production Prompt/Schema and at most one semantic recheck. New runs append the exact policy and decision and no longer read Owner Gold or `OWNER_OVERRIDE_GO`.
- `AUTO_FILTERED` now terminates without Item/Event, Owner semantic task or reader projection. `AUTO_ACCEPTED` continues through accepted claims, evidence, SourceExcerpt and the sole `PublicationService` projection boundary as machine-organized, not-human-reviewed content.
- Added forward migration `0049_autonomous_content_switch` after preserved 0048, production registry entries, least-privilege Worker append grants, migration replay, ADR-0005 and the amended #41 acceptance record. The private `.4` aggregate remains a non-authorizing reminder and its measured shortfall is not represented as a pass.
