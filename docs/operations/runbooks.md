# 运行手册执行入口

## PERS-01 本地身份与远程访问

PERS-01 仅支持单机回环访问。执行 `make dev` 后，从宿主机打开 `http://127.0.0.1:3000/sources`；Nuxt 服务端代理会删除浏览器传入的 `X-SRBG-Local-*` 头，并在 development/demo/test 环境为固定 UUIDv7 注入 `owner` 和旧读角色。API 仍只监听宿主机 `127.0.0.1` 映射。

`NUXT_LOCAL_APP_ROLES` 只控制过渡期旧页面的兼容角色，默认是 `viewer,source_admin,reviewer`；它不能移除或替代个人 API 使用的 `owner`，也不得作为远程认证机制。

不得通过反向代理、端口转发或监听地址修改把该本地身份模式暴露到局域网或公网。PERS-01 没有远程 Owner 认证；旧 OIDC 配置仅供兼容 API 使用，不能授权 `/api/v1/sources`。需要远程访问时保持服务关闭并等待后续明确设计，不得以共享 Header、关闭鉴权或把 demo 环境暴露到远程网络代替认证。

所有命令先确认目标环境。除“服务端隔离资格包 + `platform_admin` 最近5分钟 MFA”的候选启用/不启用单次决定外，生产操作必须由值班人与业务责任人双人审批；候选启用前的预算、条款和来源治理确认仍必须有可审计的责任人。

- `release`：运行全部 required checks，执行 Alembic upgrade，检查 readiness、错误预算与发布审计后逐步放量。
- `rollback`：停止 publisher/worker，回退应用镜像；保留 0012 运维事实，除隔离空库测试外不破坏性降级。
- `withdrawal`：审核员填写证据与理由，经唯一 PublicationService 撤回，验证 Feed、搜索、日报及缓存投影失效。
- `source_failure`：检查 DNS/TLS/HTTP/结构指纹；三次失败熔断，固定样本通过后影子采集并补采缺口。
- `model_anomaly`：停用异常模型/Prompt 版本，切回稳定版本，对受影响输入离线回放并进入差异审核。
- `redis_rebuild`：停 Worker，清空 Redis，从 PostgreSQL 未完成运行、Outbox、投影及 replay_request 重建后恢复 Worker。
- `internal_projection_shadow`：收到对账差异或超过 25 小时未成功告警时，停止影子回填调度，运行 `make phase2-round13-test`，并用 publisher 容器身份执行 `docker compose --project-directory . -f infra/compose/compose.yaml exec -T publisher python scripts/backfill_round13_projection.py`；核对最新 generation、`projection_reconciliation_difference`、R3/R4 数量及 active revision。差异未归零前保持默认拒绝，**不得切换第14轮消费者**，也不得让 `srbg_projection_reader_login` 回退读取业务表。
- `audit_anchor_failure`：确认原始对象存储与锚定存储 endpoint 不同、锚定桶私有且启用版本控制；修复独立存储后由 publisher 队列重跑 `srbg.audit.anchor`，或用 publisher 容器身份执行 `docker compose --project-directory . -f infra/compose/compose.yaml exec -T publisher python scripts/anchor_audit_chain.py`。核对 `audit_chain_anchor` 与独立对象内容的 audit ID/hash，一致前不得宣称链根已锚定；仅称 append-only/tamper-evident。

- `event_identity_migration`：任一 migration blocker、consumer parity 差异、alias loop、candidate backlog 或身份回滚告警触发后，立即停止 consumer switch 和新的身份变更审批。保留 Event、别名和发布修订事实，导出最新 `event_migration_run`、checkpoint、blocker 与 parity 记录并核对任务版本。别名循环必须先拒绝解析并人工复核；候选积压只能人工决定，禁止开启自动合并。切换失败时执行 application rollback，部署切换前应用版本，不降级或删除 0014 新事实；差异归零且 PublicationService 审计链复核后才能恢复切换。

- `source_governance_v2`：发生 runtime authorization mismatch 时立即停止对应来源的新采集，并核对当前生命周期事件、策略版本、连接器配置、试运行和异人审批引用；不得通过旧 `enabled` 字段恢复。policy rejection 必须按缺失的 robots、条款、版权、下载、保留或职责分离证据修正，不能降低门禁。trial security failure 必须隔离 TRIAL 数据、保留原始响应并暂停后续请求；成功试运行的 READY 比例低于 80% 时按 trial quality degradation 人工复核 raw/READY/解析失败/安全失败计数，不得以“成功”掩盖质量缺口。connector config validation 连续失败时回退到上一不可变版本，禁止改用脚本或模板。coverage gap 仅用于安排人工补齐分类和候选，不得按网址总数或 Fixture 冒充 ACTIVE 覆盖。排障期间 do not log URLs, credentials, or response bodies；审计原因不得粘贴 URL、密钥引用、Cookie、Bearer 或正文，结构化审计只记录必要对象 ID、版本、受控结果和请求 ID。

## source_governance_v2 告警处置

| 告警 | 查询与立即动作 | 恢复条件与验证 | 责任升级 |
| --- | --- | --- | --- |
| `SourceLifecycleAuthorizationMismatch` | 查询 `srbg_source_runtime_authorization_mismatches`，由 `source_admin` 暂停受影响来源并核对策略、LIVE_TRIAL、配置和异人审批；不得改写 `enabled`。 | 服务端重新计算为生产授权，运行 `make phase2-round15-test` 后才可由人工恢复。 | 15 分钟未归零升级 `platform_admin` 与合规责任人。 |
| `SourcePolicyRejectionSpike` | 按受控 reason_code 汇总，停止该来源试运行；补齐 robots、条款、版权、下载、保留和法律保全证据。 | 新策略版本经独立审核，旧拒绝事件保留；运行专项门禁。 | 升级 `source_admin`、法务/版权责任人。 |
| `SourceTrialSecurityFailure` / `SourceTrialQualityDegraded` | 保持 FIXTURE/TRIAL 隔离，核对不可变 raw、replay result 和 READY/失败计数；不得覆盖已有 READY。 | 新试运行版本通过安全检查且质量门禁满足；运行 `make fixture-replay`、`make quality-gate`。 | 升级 `source_admin` 与安全责任人。 |
| `ConnectorConfigValidationFailure` | 停止保存失败配置；执行 `CONFIG_ROLLBACK_BY_NEW_VERSION`：复制上一已审配置的非敏感字段，重新校验并创建一个新版本，禁止修改或重新激活旧不可变行。 | 新版本 Schema/hash/允许域一致，凭据仍仅为密钥引用；运行六类连接器契约与安全测试。 | 升级 `platform_admin` 和连接器代码所有者。 |
| `SourceProductionSchedulingBlocked` | 查询 `srbg_source_production_scheduling_blocked_total` 的受控 reason；保持调度为空，不得临时绑定 legacy adapter、脚本或动态目标。 | 仅在后续明确授权轮次交付经评审的 definition+config+executor+target 绑定并运行 `make phase2-round15-test` 后恢复。 | 立即升级 `platform_admin`；需要扩大产品范围时停止并请求业务责任人决定。 |
| `SourceCoverageGapDetected` | 查看五维覆盖矩阵，安排人工候选与分类修正；不以 Fixture 或网址总数消除缺口。 | 缺口由经审批的真实 ACTIVE 来源消除，或由责任人接受并记录例外。 | 升级来源治理责任人。 |

所有查询和日志只允许 `event_name/action/outcome/reason_code/request_id/source_id/object_id` 等受控字段；do not log URLs, credentials, or response bodies。

# 自动化来源发现、资格审查与启用

## 运行状态与授权边界

自动化链路是“发现候选 → 直接目标核验 → 隔离资格审查 → 管理员决定 → 新生产采集”，不是“搜索结果直接入库或发布”。生产启用前必须同时满足：

- Alembic 已到 `0018_source_automation`，PostgreSQL、私有对象存储、ClamAV、Redis/Celery 和审计链健康；
- 企业 OIDC/SSO 已配置 `platform_admin`，`acr`、`amr=mfa` 和 `auth_time` 可验证；最终启用或不启用时 `auth_time` 不得早于5分钟；本地身份例外只允许明确的 demo/test 环境并要求本地 step-up；
- 来源治理责任人已确认固定查询目录、目标行业/内容域、目标站点 robots/服务条款/版权、展示与下载边界；不得把资格规则的 `WARN` 当作法律意见；
- 财务/平台责任人已确认百度前1500次/月免费、其后0.036元/次、80%一次告警和200元/月硬上限，并验证当前百度合同价格仍与代码模型一致；价格或接口合同变化时先关闭发现，再评审代码，不能只提高环境变量；
- 百度 API key 只存在于批准的 Secret 配置。固定查询目录本身受代码评审，但日志、Celery 消息、审计理由和工单中不得出现 key、Bearer、单次查询记录、标题、摘要、响应体或候选 URL。

默认配置是：

```dotenv
SRBG_SOURCE_DISCOVERY_ENABLED=false
SRBG_SOURCE_QUALIFICATION_ENABLED=false
SRBG_BAIDU_SEARCH_ENABLED=false
SRBG_BAIDU_SEARCH_API_URL=https://qianfan.baidubce.com/v2/ai_search
SRBG_BAIDU_SEARCH_API_KEY=
SRBG_BAIDU_SEARCH_FREE_CALLS_PER_MONTH=1500
SRBG_BAIDU_SEARCH_COST_PER_CALL_MICRORMB=36000
SRBG_BAIDU_SEARCH_BUDGET_ALERT_BPS=8000
SRBG_BAIDU_SEARCH_MONTHLY_CAP_MICRORMB=200000000
```

只有完成上述确认后，才允许从 Secret 注入 API key，并同时显式开启 `SRBG_SOURCE_QUALIFICATION_ENABLED`、`SRBG_SOURCE_DISCOVERY_ENABLED` 和 `SRBG_BAIDU_SEARCH_ENABLED`。Worker 启动时会拒绝非钉死的百度 HTTPS origin/path、空 key、只开百度而未开来源发现、开启自动发现但关闭资格审核、单次成本高于月上限等配置。资格审核可以在关闭百度和自动发现时单独启用，以处理手工候选和既有来源续期。每6小时一次的 Beat 只发送代码固定的查询代码与 `discovery_run_id`，不能由请求或消息注入任意查询。

启用后先观察一个调度周期，不批量启用候选。确认任务结果仅含有界计数、`source_provider_usage` 正确记账、候选来自目标站点直连证据、资格捕获在私有隔离空间且审计链连续，再逐项放量。当前自动调度器只有百度通道；`DIRECTORY/RSS/SITEMAP/OUTBOUND_LINK` 仅为候选来源渠道契约，不能按多通道已上线验收。

## 候选决定

`source_admin` 可以登记手工 HTTPS 机构地址、查看证据和重新资格审查，但不能启用或不启用；最终决定只能由 `platform_admin` 在 `/admin/sources?view=candidates` 完成。操作时：

1. 核对机构域、服务端分类、材料指纹、规则版本、资格包 SHA-256、检查项、存储/捕获政策和7天有效期。
2. `QUALIFIED` 可单项启用；`WARN_WAIVABLE` 只允许单项启用并填写具体豁免理由。若证据捕获政策不是 `PRIVATE_RAW_ALLOWED`，生产启用仍会被数据库拒绝。`BLOCKED` 只能不启用或重新资格审查，永远不能豁免启用。
3. 材料指纹、资格包、规则版本或有效期发生变化时，服务端返回409；刷新候选并重新判断，不得自动重试旧决定。
4. 批量启用只用于1—10个同规则版本、未过期、`QUALIFIED` 的候选；预检整体失败时不写任何项，执行阶段每项独立事务并返回逐项冲突，不得把部分成功伪装成原子全成功。
5. 启用成功只代表来源/默认流获得生产采集资格。Outbox 随后创建新的 `SCHEDULED + PRODUCTION` 运行；必须在运行中心验证新 `run_id` 的 raw-first 结果。资格审查的对象、哈希或运行不得改写 execution domain，也不得复制为生产结果。

手工 URL 与百度候选共用同一资格和决定路径。自动登记产生的通用 `LIST_DETAIL` V1 连接器只能作为首版结构假设；若目标站点不是通用列表页，先暂停来源，以追加新配置版本的方式修正并重新资格审查，禁止直接修改不可变配置或在生产临时注入选择器脚本。

## 预算、隐私与安全监控

每次百度 I/O 前，Worker 在 `source_provider_usage` 中按 UTC 月加行锁并预留调用次数/费用。前1500次的新增费用为0；此后每次增加36000微元人民币。一次调用即使供应商超时或返回无效响应也已占用预留次数/费用，不能靠重试回退账本。到80%时只记录一次 `baidu_search_monthly_budget_threshold_reached`；等于200元可以保留，下一次会超过上限的请求在网络 I/O 前返回预算停止。不得手工减少 `request_count`、`cost_micrormb` 或清空 `alerted_at`。

只读核对使用低敏字段：

```sql
SELECT provider, utc_month, request_count,
       cost_micrormb, monthly_cap_micrormb, alerted_at, updated_at
  FROM source_provider_usage
 WHERE provider = 'BAIDU_SEARCH'
 ORDER BY utc_month DESC
 LIMIT 3;

SELECT status, count(*) AS candidate_count
  FROM source_candidate
 GROUP BY status
 ORDER BY status;

SELECT verdict, count(*) AS bundle_count
  FROM source_qualification_bundle
 GROUP BY verdict
 ORDER BY verdict;
```

监控 `srbg_source_automation_candidate_backlog{status=...}`、`srbg_source_automation_qualification_requests_total{trigger,outcome}` 和 `srbg_source_automation_candidate_decisions_total{decision,outcome}`。标签只能使用代码枚举；禁止增加 URL、source/candidate UUID、规则自由文本、供应商查询或错误正文标签。Worker 的发现结果同样只允许 `provider_calls/provider_failures/budget_stops/budget_alerts/targets_seen/targets_probed/targets_rejected/candidates_registered/qualifications_requested` 等计数。

固定查询目录保存在代码中；单次百度调用记录及结果标题、摘要不写运行时持久化，也不进入日志、审计或消息。这不等于供应商不知道收到的固定查询。禁止把内部项目名、人员名、事故未公开信息、密钥或用户输入拼接到查询目录。候选只有在共享 HTTP 安全边界完成 DNS 全地址检查、实际 peer IP 固定、每跳重定向复核、HTTPS 机构边界、大小/超时限制和目标内容哈希后才能登记。

## 自动更新、异常与受控修复

启用后的自动更新复用 PostgreSQL `fetch_schedule`。每次物理请求前重读 ACTIVE 来源、当前批准政策、VALID 配置、有效生产审批、流/计划状态、请求与字节预算及熔断；Redis 只传递 ID。连续5次计入熔断的失败打开30分钟熔断，半开只允许受控探测；连续3次零发现生成 `ZERO_DISCOVERY_STREAK`，它是“传输可能成功但发现失败”的异常，不能按健康成功处理。

受控修复顺序：

1. 从 `/api/v1/admin/source-attention` 和运行中心确认受控 reason code、最近运行/计划 ID 和异常时间；不要把 URL 或响应正文复制到日志。
2. 通过既有来源生命周期/计划接口暂停对应来源或计划。当前来源流投影会返回 `PAUSE/RESUME/REQUEST_REPAIR/REVOKE` 建议动作，但自动化来源 API 尚未提供独立流动作写端点，不能直接修改 `source_stream.status` 冒充修复。
3. 按故障类型核对 DNS/TLS/HTTP、robots/条款、结构指纹、连接器配置版本、对象存储和预算。配置修复必须追加新版本；来源材料或授权变化必须重新资格审查。
4. 用固定样本/隔离回放验证，再进行一次受控半开或新生产采集。确认 raw-first、解析质量、发现数量、审计和预算均正常后才恢复计划；不得清零失败数、关闭异常或改写历史运行来制造健康。

## 生产 READY 文档的内容处理交接

`SCHEDULED + PRODUCTION` 文档成为当前 `READY` 后，数据库触发器会写入
`source_content_outbox(PENDING)`；Beat 每5秒仅投递 `outbox_id`，数据库命令在同一事务中
创建 `ai_pipeline_run(LIVE, QUEUED)` 并把 Outbox 标为 `WAITING_AI`。该状态只表示已耐久
交给受控 AI 队列，不表示已分类、已形成 Claim、已人工审核或已发布。

- `PENDING/FAILED` 积压：先核对 Parser Worker、PostgreSQL 和迁移版本，不从 Redis 拼装
  URL、正文或模型请求。修复后等待 Beat 重新投递同一 Outbox ID；人工优先重放也只能
  重投该 ID。
- `DEAD_LETTER`：保留 Outbox、文档版本和 raw 证据，核对受控 `last_error_code`。禁止修改
  `attempt_count`、直接插入 AI 运行或把状态手工改成 `WAITING_AI`；普通重放不得绕过5次上限，
  修复代码/权限后必须通过带审计和专项验收的向前修复迁移恢复。
- `WAITING_AI` 长期积压：这不是发布故障。当前通用生产 AI 四步编排器尚未交付时，记录
  应诚实停留在这里。不得创建 UNKNOWN 条目、空 Claim、默认 accepted Claim 或伪造审核
  任务来清空队列。
- 交接前版本已被替换、隔离或原始安全事实失效：保持失败/死信，并由来源管理员核对新
  当前版本；旧版本不得进入 AI 或发布链路。

任何后续处理仍须形成服务器校验的候选 Claim/双向 Evidence、进入 R3/R4 服务端审核，
最终只由 `PublicationService` 改变发布状态。

## 停止、回滚与密钥事件

- 只停止付费发现、保留已排队资格审查：设置 `SRBG_BAIDU_SEARCH_ENABLED=false` 并重启 Worker。它停止新百度查询，但不暂停已经 ACTIVE 的来源。
- 停止付费自动发现但保留手工/续期资格审核：设置 `SRBG_SOURCE_DISCOVERY_ENABLED=false` 和 `SRBG_BAIDU_SEARCH_ENABLED=false` 并重启 Worker；不要关闭 `SRBG_SOURCE_QUALIFICATION_ENABLED`。
- 停止全部资格目标探测：另行设置 `SRBG_SOURCE_QUALIFICATION_ENABLED=false` 并重启 Worker。待处理资格任务保持数据库待处理事实，不会被伪造成通过或阻断；恢复前不得手工改成 READY。
- 停止已启用来源的生产更新：另行使用来源生命周期/计划暂停；关闭发现开关不会撤销既有生产审批、流或计划。
- API key 疑似泄露：立即关闭百度开关、在 Secret 管理系统吊销/轮换 key、检查供应商审计和 `source_provider_usage` 异常增量。禁止在排障输出中打印旧 key 或 Authorization header。
- 应用回滚：先关闭发现与资格探测，暂停受影响的自动来源，再回退 API/Worker 镜像；保留 `0018`/`0019` 表、Outbox、审计、隔离证据和生产运行。不能消费新表的旧应用不得写这些事实。
- 数据库回滚：只有隔离环境且 `source_content_outbox` 无事实，且 `source_candidate`、`source_candidate_decision` 和 `source_qualification_bundle` 均无事实时才允许 downgrade；内容交接存在时先返回 `ROUND19_DOWNGRADE_BLOCKED`，自动化治理事实存在时再由 `ROUND18_DOWNGRADE_BLOCKED` 拒绝。生产恢复以向前修复为主，禁止删除 Outbox、候选、资格包或决定以强行降级。

| 事件 | 立即动作 | 恢复条件 |
| --- | --- | --- |
| 月预算80% | 核对合同价格、当月请求增量和调度频率；禁止提高阈值 | 责任人确认本月余量；只读账本一致，告警保持单次 |
| 月预算100%/预算停止 | 保持自动停止，不绕过账本或换 key 继续请求 | 下个 UTC 月自然新建账本，或经新产品/预算评审发布代码 |
| 供应商响应异常 | 关闭百度发现；保留有界失败计数，不记录异常正文 | 钉死端点、Schema、DNS/peer 和价格合同重新通过测试 |
| 候选误分类/噪声激增 | 停止发现；不启用候选，检查固定查询代码和直接目标证据 | 查询目录代码评审、固定样本回放和候选抽检通过 |
| 资格原始证据越域 | 立即停止资格 Worker 和激活 Outbox，暂停相关来源 | 证明隔离对象未进入 PRODUCTION，完成安全审计和向前修复 |
| 陈旧资格包409 | 刷新候选，不重试原决定 | 新材料重新资格审查且管理员重新作出决定 |
| 启用后首次生产采集失败 | 暂停来源/计划，保留 Outbox 和新生产 `run_id` | 修复配置并以新生产运行验证，不复用资格响应 |

恢复演练运行 `make recovery-drill`；该目标显式传入 `--isolated-only`，脚本仍会拒绝预生产和生产环境，并且只使用随机数据库、桶和 Redis DB 15。
# Round 16 scheduling, health and replay

- `source_false_success`: pause the schedule, compare the latest health snapshot with raw evidence, and resume only after discovery, parser and policy checks pass.
- `queue_backlog`: inspect PostgreSQL `fetch_run` and leases first; reclaim expired leases with the same run id and never manufacture work from Redis.
- `redis_rebuild`: stop consumers, enumerate durable pending runs and replay requests, republish only `source_id/run_id`, then verify idempotent completion.
- `object_storage_unavailable`: retain the database run with bounded backoff, open the circuit when retries are exhausted, and create no document version without durable raw evidence.
- `retention_mistake`: stop retention workers, preserve hashes and metadata, restore only from an approved private backup, reconcile through PublicationService, and audit the recovery.
- `safe_replay`: require platform-admin authorization, reason and idempotency key; re-read current policy and authoritative references, otherwise mark `NON_REPLAYABLE` or `BLOCKED`.

# Round 17 real-pilot observation

- `round17_preflight`: keep `SRBG_ROUND17_LEO_APPROVER_ACTOR_ID`, baseline commit,
  config version and exact 20-code roster unset until the corresponding external approvals exist.
  The LEO actor value must be the approved non-local OIDC UUIDv7; a matching display name or role
  alone is insufficient. Window lifecycle, gold arbitration/release and operator-time correction
  all fail closed when that actor attestation is missing or different.
- `round17_source_pause`: keep the affected source segment `PAUSED`, retain its immutable
  policy/config/schedule pins, and verify the other nineteen source segments remain scheduled.
  yinzi records only the source ID, bounded reason code, versions and elapsed work category. A
  connector, DOM, policy, schedule or approval change requires a new version and separately
  reported observation segment; never edit the running segment or silently fill the gap. Replay
  is diagnostic only and cannot enter the real-window numerator.
- `round17_evidence_contamination`: immediately stop acceptance evaluation when
  `srbg_round17_contaminated_runs` is non-zero. Identify the run by PostgreSQL IDs, remove it from
  the immutable evidence export, and prove its `run_origin`/`execution_domain` classification.
  Do not delete raw facts or relabel Fixture, replay, backfill, drill or TEST runs as scheduled real
  responses. Resume evaluation only after an independent query shows zero linked contamination.
- `round17_operator_timer`: a timer must reference the active UUIDv7 window and the controlled
  OIDC identity bound as `SOURCE_OPERATOR`. The UI heartbeats every 60 seconds; the server counts
  no more than 15 minutes between heartbeats and never records notes, URLs or content. For a stale
  timer, stop it, use one bounded correction reason code if needed, retain the correction audit,
  and report source maintenance, exception handling, R3 review and copyright/correction
  separately.
- `round17_fault_drill`: use only an approved source pause or an isolated TEST transport/DNS/
  object-store fault. Record approval, T0/T1, alert, pause, replay, recovery and yinzi's actual
  handling time. Never degrade, flood or alter a real external source to manufacture the drill.

Round 17 cannot be marked complete until LEO has confirmed the exact roster, metric/gold
definitions and immutable 168-hour window, all twenty sources have honest evidence or explicit
no-update health, and the offline eval passes. Missing external facts remain `BLOCKED`.
