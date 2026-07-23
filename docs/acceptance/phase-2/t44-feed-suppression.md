# T44 Feed suppression acceptance

Issue #44 implements the Feed preference slice under parent Spec #40. It reuses the frozen `FeedSuppressionCommand`, `FeedSuppressionRuleView`, and existing append-only `feed_suppression_rule_v2`; it does not add a second suppression store, Safety allow/deny, or technical retry behavior.

## Preconditions and isolation

- Fetched `origin --prune` before worktree creation.
- Based branch `codex/issue-44-feed-suppression` on remote integration merge `1c2a170925099dedaf822b2c5219e493889bb4c6`.
- Verified #43 feature commit `ec2718518e3c6806a96e636c11b67eefcbc30943` is an ancestor of the remote integration branch.
- Created clean independent worktree `D:\CodexProjects\srbg-intelligence-platform-issue44`.
- Confirmed one Alembic head, dynamically extending `0051_technical_exception_recovery` with `0052_feed_suppression_projection`.
- Used Compose project `srbg-issue44` with dedicated named volumes and ports: PostgreSQL `55444`, Redis `56444`, MinIO `59444`, anchor MinIO `59445`, MinIO console `59446`, API `58444`, and Web `30444`. No #43 service, data, port, branch, or checkout was reused.

## Delivered behavior

- Owner list/activate/revoke API requires local Owner identity. Commands use UUID idempotency keys; revoke additionally requires `If-Match` for the activation rule. Same-payload revoke replay returns the original result before reconstruction work; reusing a key with different content or racing a duplicate activation fails without a second append.
- Revocation revalidates every matched current projection before appending the irreversible REVOKE fact. Infrastructure failures therefore leave the original suppression active and safely retryable; current gate denials remain fail-closed. If two different revoke keys race, the loser reruns the authoritative gate after the winner's database timestamp so an older provisional refresh cannot leave content hidden.
- `SAFETY_DENIAL` remains in the frozen shared contract but is deliberately rejected by this endpoint. Only `OWNER_PREFERENCE` and `CLASSIFICATION_ERROR` are implemented here.
- Migration 0052 adds a rebuildable `event_suppression_match_v2`, active/revoked rule view, visible projection security-barrier view, and the Event authority needed by media delivery. It backfills existing projections and keeps a single linear head.
- Publication projection writes rebuild EVENT, PRIMARY_TYPE, ENGINEERING_OBJECT, SPECIALTY_FACET, EQUIPMENT_DOMAIN, every Event-bound SOURCE, and normalized confirmed custom-topic keys in the same transaction as Feed/search projection writes. Migration backfill and runtime use the same NFKC/casefold/whitespace normalization; legacy topic titles outside the frozen 300-character/control-character contract are safely ignored rather than breaking projection refresh.
- Feed, search, hotspot, Event detail, ReaderAppendix, media preview, and media download all join the server-visible projection in SQL. Filtering therefore precedes ranking, cursor evaluation, pagination, and `LIMIT`; no complete suppressed response reaches the browser.
- Activation changes only visibility. It does not delete RawResponse/raw objects, documents, evidence, accepted claims, qualification or publication decisions, audit history, or the append-only rule ledger.
- Revocation remains append-only. Affected current documents re-enter only by executing the existing `PublicationService` reconstruction and current authoritative gates. Passing content receives a projection timestamp after the revoke and restores automatically; denied content remains unavailable. No second Owner approval is introduced.
- The shared Nuxt Feed card and unified Event Reader offer a confirmed Event hide action. `/feed-suppressions` lists active rules, supports all frozen scopes with exact keys, and revokes with idempotency and concurrency headers. HTTP 412 conflicts receive an explicit refresh/retry state; keyboard-sized controls, responsive layout, and axe tests cover the Owner workflow.
- Metric `srbg_owner_feed_suppression_commands_total` uses only bounded `scope`, `action`, and `outcome` labels. Every accepted append also enters the tamper-evident audit chain.

## Verification evidence

- Focused API/migration/publication/SQL/observability tests: the final dedicated #44 set passed 16/16.
- Real migration upgrade, downgrade to 0051, and re-upgrade to 0052 passed against the independent PostgreSQL instance.
- Extended autonomous migration replay passed `0048 -> 0049 -> 0048 -> 0049 -> 0050 -> 0049 -> 0050 -> 0051 -> 0050 -> 0051 -> 0052 -> 0051 -> 0052`.
- The single existing highest SourceStream acceptance module passed 7/7, including two AUTO_ACCEPTED publication paths where SOURCE rules predate the real fetch/raw/document handoff, Event suppression/removal from Feed, search, hotspot, detail, appendix and real object-storage media delivery, same-key revoke replay, automatic gated restoration, preservation of raw objects/document versions/claims/evidence/decisions/audit, and controlled two-writer activation/revoke races with exactly one append winner and a visible converged read model.
- Focused Nuxt unit tests and Vue strict typecheck passed.
- Full repository tests passed: Python `1515 passed, 27 skipped`, UI `53 passed`, Web `106 passed`, and contract tests `122 passed`.
- Lint and strict type checking passed for Python, contracts, UI, and Web. Fixture replay passed `374` tests and the Round 09 offline evaluation reported `passed: true`.
- Security checks passed: Python and production Node dependency audits reported no known vulnerabilities, and Trivy reported no HIGH/CRITICAL secret or configuration findings.
- Browser gates passed against the independent API/Web stack: Playwright E2E `77 passed` and axe accessibility `25 passed`.
- Two independent code-review passes identified revoke ordering, multi-source/custom-topic matching, Reader action, Unicode length handling, observability, and highest-seam coverage gaps. All valid findings were fixed and their affected gates rerun; no known valid finding remains open.

No changes were pushed or merged and no Issue was closed.
