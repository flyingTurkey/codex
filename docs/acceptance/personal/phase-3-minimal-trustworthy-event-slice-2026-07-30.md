# 第三阶段：最小可信资讯纵向切片验收记录

日期：2026-07-30

分支：`codex/phase-3-trustworthy-event-slice`

`PHASE_2_SHA`：`6df8ce1a856bd26718c4efb532381c5437e8266a`
基线验证：`a83dda4` 是 `PHASE_2_SHA` 的祖先；工作分支从该精确 SHA 创建。

## 目标与边界

本阶段只关闭第二阶段诊断已经证明会阻塞第一条可信 Event 的缺口。保留既有 SourceAdapter、raw-first、SourceStream、证据候选和 Reader 架构，没有移植历史迁移或制造第二套发布通道。

验收完全使用一次性 PostgreSQL、Redis、私有 MinIO bucket 和独立对象 namespace。输入是仓库内最小化英文 fixture；没有公网访问、真实来源、真实模型、正式数据库或受版权保护全文。

明确未实现：stop/drain 控制面、governed replay UI、operations/readiness dashboard、高级 Feed 筛选、campaign ledger、多来源、三种主类型全面扩展和安全敏感事实自动发布。

## 已关闭的已证实缺口

1. Worker 在 `SUMMARIZE` 后进入 `VERIFY`，确定性 adapter 仍经过真实 provider 使用的 Prompt、JSON Schema、Pydantic、evidence locator、失败分类和 Token/费用接口。
2. `VERIFY` 成功在同一 Worker 事务中落下 step、SourceExcerpt、approved success、summary success/outbox、pipeline success 和 handoff 终态；回调校验失败仍结算可验证的真实响应费用。
3. evidence anchor 拒绝具有稳定非正文错误码；claim/evidence 双向引用在 gateway 和服务端物化边界重复校验。
4. `PublicationService` 在单一 Publisher 事务中创建或复用自动发布 authority、publication/revision、FULL/search/suppression projection 和 publication decision。
5. Reader FULL 可见性绑定 current publication revision、current document、accepted-claim SHA-256、VERIFY step、SourceStream definition/config SHA-256、authority epoch 和 Owner veto。
6. Owner veto 立即 fail closed，恢复授权产生新 epoch/revision；过期投影刷新不能把 `projected_at` 倒退。
7. Worker 通过窄 `SECURITY DEFINER` 命令锁定 handoff，Publisher 通过窄命令加载并锁定自动发布权威上下文；Reader 只读取 security-barrier view。

## 迁移

- 新 revision：`0055_phase3_trustworthy_event`
- `down_revision`：`0054_policy_optimization`
- 未修改 `0001`—`0054`，未使用 merge revision。
- 隔离回放：`0054 -> 0055 -> 0054 -> 0055`
- 回放验证：
  - 新表、列、约束和 VERIFY registry 的存在/撤销；
  - SourceStream config/definition hash 权威；
  - Worker/Publisher 窄函数 EXECUTE 和直接 UPDATE 否定权限；
  - Reader 仅可读取 guarded view；
  - VERIFY 预算预留函数升级/降级；
  - 自动 authority 表保持空基线，未用 SQL fixture 造最终 Publication。

## 纵向验收链

`SourceAdapter -> private raw object -> DocumentVersion -> qualification -> CLASSIFY -> EXTRACT -> SUMMARIZE -> VERIFY -> accepted claims/evidence -> SourceExcerpt -> PublicationService -> /api/v2/feed -> Event Reader`

自动断言覆盖：

- raw object、DocumentVersion 和 SourceStream authority 均来自真实业务入口；
- 四个模型步骤使用同一确定性 gateway/callback；
- claim/evidence 双向引用及精确 locator；
- `source_published_at`、`first_discovered_at` 和 UTC 时间语义；
- 错误有稳定分类，费用失败不静默；
- outbox、authority、revision、projection 和 handoff 重放零重复；
- FULL 仅由 `PublicationService` 产生，Reader 可读；
- R3 只投影允许的待审核元数据，R4 不可读取；
- FULL 标记 `human_reviewed=false`，即“机器整理/未人工复核”；
- Owner veto 隐藏，恢复后由新 authority epoch/revision 重新可见。

## 门禁记录

- `make check-fast`：通过；risk plan 无 unknown path，Python affected tests 为 `1307 passed, 27 skipped`，契约为 `123 passed`。
- `make check-pr`：通过；Python unit/infrastructure 为 `1495 passed, 27 skipped`，隔离集成为 `13 passed`，第三阶段纵向集成为 `10 passed`；migration up/down/up、契约、最小权限和发布路径审计均通过。
- `make check-release`：已在 release candidate 上执行唯一一次；后端、迁移、隔离集成、安全、契约、发布对抗和 `web-build` 等前序门禁通过，随后 `web-e2e` 因隔离工作树缺少本地 Playwright Chromium 可执行文件而失败。78 项浏览器用例均为同一个 `browserType.launch` 环境错误；未联网下载浏览器，且按单次运行约束未重跑。
- `make check-live`：未运行，任务明确禁止。
- 真实来源、真实模型和正式数据库：未运行。`check-release` 虽调度了全量浏览器用例，但浏览器进程均未启动。

## 冻结状态

- `RELEASE_CANDIDATE_SHA`：`1fc0d127a9861f119996d6443b103bcdc9d8b54b`。
- 本地 `check-release`：失败；唯一失败门禁为 `web-e2e`，原因是本地 Playwright Chromium 缺失，不是测试断言或本阶段代码失败。不得据此宣称 release 门禁全绿。
- 远端 CI：未触发；没有 Owner 单独推送授权。
- live 验收：未运行。
- `git status`：关闭记录提交后最终复核为 clean。

## Authorized release retry and deterministic Web image correction

The earlier release-candidate result is retained as historical evidence: its only
terminal failure was the absent Playwright executable. The Owner subsequently
authorized offline-browser preparation, Docker Desktop restart, a release retry,
and an exact-SHA branch push for remote CI.

The retry exposed a separate pre-freeze build defect before any release result was
accepted. `Dockerfile.web` mounted the BuildKit pnpm cache at
`/home/node/.local/share/pnpm/store`, while pnpm 11.12.0 used
`/workspace/.pnpm-store/v11`. The image therefore re-downloaded dependencies and
re-ran registry-wide lockfile policy checks on every rebuild. The permanent
correction:

- mounts and explicitly selects `/workspace/.pnpm-store`;
- retains `--frozen-lockfile`;
- uses pnpm's documented `--trust-lockfile` mode for this reviewed closed-source
  lockfile, while leaving the independent dependency audit/security gate intact;
- adds infrastructure contract coverage for both the cache path and reviewed
  lockfile boundary.

Pre-freeze evidence after the correction:

- focused infrastructure contract: `28 passed`;
- `make check-fast`: PASS (`1308 passed, 27 skipped`; contract `123 passed`);
- `make check-pr`: PASS, including the single migration head, `0054 -> 0055 ->
  0054 -> 0055`, isolated PostgreSQL/Redis/private-MinIO integration,
  PublicationService path audit, AI/evidence adversarial tests, and Compose smoke;
- the 27 skips are the same explicitly audited integration-environment skips
  recorded separately; there is no unexplained skip or temporary bypass.

## 第三阶段终态发布记录

本节只补齐冻结候选的终态证据，不改写上文第一次冻结失败的历史记录。

- `RELEASE_CANDIDATE_SHA`：`bcc81f2138c7c85f0b57edc344568a62f64363f0`。
- 本地 `make check-release`：在该 SHA 上通过，耗时 502 秒；包括
  diff/docs、Ruff/mypy、Python/Web/contract、migration、安全、fixture、
  acquisition、隔离集成、AI/证据/发布对抗、Web build、78 项 E2E 和
  25 项 a11y 门禁。
- 远端 CI：同一 SHA 全绿；GitHub Actions run `30539022097` 于
  `2026-07-30T11:37:52Z` 完成。
- live 验收：按阶段约束未运行；没有运行 `make check-live`，没有访问真实来源、
  真实模型或正式数据库。
- skip：27 项 Python skip 已逐项审计为环境特定集成目标；远端跳过步骤均为条件
  不适用。不存在未解释 skip、失败或临时绕过。
- 发布和迁移不变量：`PublicationService` 唯一发布路径审计通过；Alembic 只有
  `0055_phase3_trustworthy_event` 一个 head，且
  `0054 -> 0055 -> 0054 -> 0055` 隔离往返通过。
- 候选工作树：本地 release 验证前后均为 clean；候选 SHA 在本收口记录提交前
  已推送到远端并完成同 SHA CI。

`bcc81f2138c7c85f0b57edc344568a62f64363f0` 始终是不可变的第三阶段
release candidate。本次仅文档收口的后继提交不是新的 release candidate。
第四阶段可据此候选和本收口记录评估启动门禁；本次不创建第四阶段或第五阶段
分支，也不启动其任务。
