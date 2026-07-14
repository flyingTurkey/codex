# Round 02 首个安全规定 HTML 来源验收记录

- 日期：2026-07-14
- 来源范围：仅应急管理部 `GOV-006`
- 生产准入状态：`CANDIDATE`、连接器 `disabled`
- 确定性验收来源：经真实 `SourceRegistryService`、30 个不同固定样本和完整准入证据激活的隔离测试来源

## 用户场景与边界

定时任务从已准入的应急管理部公开规章列表发现新文件，保存原始 HTML，再解析标题、发布机关、文号和发布日期并生成段落证据。R3 内容先进入人工审核：普通用户只能看到标题、类型、官方来源、原文发布时间、首次发现时间、原文链接和“待审核”；职责分离的审核员核对证据并批准后，唯一 `PublicationService` 通过 v2 默认拒绝门禁，内容才以完整卡片进入安全频道和详情页。

本轮不做 PDF/OCR、事故、AI 摘要、复杂修订关系或真实评分。评分允许缺省；无真实评分的内容不得进入 `/selected`，Feed 契约不含 `scores`。待审 `publication_revision_id` 为 `null`，发布成功后才绑定不可变修订号。

## 官方样本与联网记录

联网操作按要求通过 `web-access` skill，在隔离浏览器中只访问公开页面并固化响应字节：

- 列表页：`https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/gz11/index_1.shtml`
- 详情页：`https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/gz11/201606/t20160603_405633.shtml`
- 固定响应、SHA-256、字节数和原始 URL 绑定在 `apps/api/tests/fixtures/source/round02-mem-fixture-manifest.json`；真实抓取只作为可配置适配器，确定性门禁不依赖在线可用性。

## 交付切片

- `SourceAdapter` 是唯一采集协议，`SourceConnector` 只是兼容别名；`DocumentParser` 是唯一解析协议。Worker 每 15 分钟只枚举服务端有效准入且启用的 `MEM_SAFETY_REGULATION_HTML` 连接器。
- 采集实现条件请求、URL/主机白名单、DNS 全地址公网校验、连接对端校验、重定向再校验、响应大小上限、退避重试、限速、持久化失败计数、五分钟熔断和连接器/外部 ID 幂等。
- 原始 HTML 先写私有对象存储和不可变文档版本，再执行规则解析与语义安全扫描。字段证据双向绑定到 `html-p-NNNN`、字符区间、摘录 SHA-256 和原文 URL。
- 受控分类为 `DEPARTMENT_RULE`；文号规则同时覆盖原国家安全监管总局令和应急管理部令，不绑定固定第 88 号；发布日期证据由服务端解析出的日期动态定位。法规效力默认 `UNKNOWN`。
- Alembic `0003_safety_publication` 新增 `source_checkpoint`、`fetch_run`、`fetch_record`、`processing_run`、`intelligence_item`、`safety_regulation_profile`、`claim`、`claim_evidence`、`review_task`、`publication`、`publication_revision`，并为发布修订、Claim 和证据设置不可变触发器。
- `PublicationService` 是审批、拒绝、修订、撤回和重发的唯一应用入口。它在同一发布事务中锁定审核任务，现查来源准入、当前政策与哈希、30 个准入样本、当前文档版本与哈希、证据覆盖、语义安全、审批人和职责分离，再执行 `publication_gate.json` v2。
- PostgreSQL 只向 `srbg_publication_writer` 授予 `publication`/`publication_revision` 写权限。API、Worker、管理员和模型数据库角色继承的运行时角色均无直写权限；API 使用独立发布连接执行 `PublicationService` 事务。
- `FeedPage`、`ItemSummary`、`FeedNotice`、`TypeSummary` v1 已冻结。`GET /api/v1/feed?mode=selected|all` 返回扁平 Cursor 列表，由前端按 `Asia/Shanghai` 对 `activity_at` 分组；BFF 保留查询串并覆盖浏览器自报的本地角色头。
- `/`、`/selected`、`/all`、`/digital`、`/safety` 复用 `IntelligenceFeedPage`、`TimelineFeed` 和 `IntelligenceCard`；详情、证据抽屉和审核工作台共享同一证据及发布契约。

## 迁移与回滚

已在本地 PostgreSQL 实际执行 `0002_source_vault → 0003_safety_publication`，并实际降级到 `0002_source_vault` 后重新升级到 head。回滚命令：

```powershell
$env:SRBG_DATABASE_URL='postgresql+asyncpg://srbg:srbg_local_only@127.0.0.1:15432/srbg'
.\.tools\uv\uv.exe run alembic -c apps/api/alembic.ini downgrade 0002_source_vault
.\.tools\uv\uv.exe run alembic -c apps/api/alembic.ini upgrade head
```

生产回滚前必须备份 PostgreSQL 和私有对象存储；降级删除本轮业务表，但不会自动删除不可变原始对象。

## 关键验收场景

- 固定列表出现一条新规定后只创建一个原始文档、当前版本、情报项和审核任务；再次运行使用列表游标/ETag，不重复创建。
- 待审普通投影的 `publication_revision_id=null`，响应不含文号、机关、效力、Claim、证据、AI 摘要、伤亡、归责、原因或评分；审核详情端点仅 reviewer/auditor 可读。
- viewer 审批返回 403；R3 提交人审批自己的任务被服务端与数据库约束共同拒绝。
- 独立审核员批准后，服务端 v2 门禁通过，生成不可变 `publication_revision`，安全频道和详情返回规则字段及段落证据。
- 普通发布无评分可通过人工审核；同一内容仍不会进入 `/selected`，Feed/生成 TypeScript 契约均不存在 `scores` 字段。
- `srbg_api_login` 直接插入 `publication` 被 PostgreSQL 拒绝；`srbg_publisher_login` 只能通过专用仓储写入，RBAC 测试同时核对 API、Worker、管理员和模型组权限。
- 连接器发现失败写入失败运行；连续失败达到阈值后持久化熔断，熔断期只记录 `CIRCUIT_OPEN` 运行而不访问来源。

## 最终门禁

本轮最终验收实际执行：

```text
make lint
make typecheck
make test
make contract-test
make security-check
make fixture-replay
make safety-regulation-test
make web-e2e
make web-a11y
make quality-gate
```

结果记录：

| 门禁 | 结果 |
|---|---|
| `make test` | 103 Python 通过、3 个显式集成开关跳过；UI 52 通过；Web 30 通过 |
| `make contract-test` | 17 通过；Python/JSON Schema/TypeScript 生成前后字节可重复 |
| `make fixture-replay` | 29 通过，包含官方固定样本、解析、采集安全、管线和发布门禁 |
| `make safety-regulation-test` | 2 个真实 PostgreSQL/MinIO 集成场景通过 |
| `make web-e2e` | Chromium 24 通过，含四个响应式视觉基线 |
| `make web-a11y` | axe 4 通过，`violations=[]` |
| `make security-check` | pip-audit 无已知漏洞；pnpm 仅 1 个 low；Trivy HIGH/CRITICAL 为 0 |
| `make quality-gate` | lint、typecheck、test、contract-test、security-check 全部退出 0 |

采集结果保存在 `fetch_run`/`fetch_record`/`source_checkpoint`，审核与发布动作写入哈希链 `audit_log`；Worker 记录结构化来源 ID 和失败事件，可据连续失败、熔断状态和待审积压建立运行告警。
