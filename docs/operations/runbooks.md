# 运行手册执行入口

所有命令先确认目标环境，生产操作必须由值班人与业务责任人双人审批。

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

恢复演练运行 `make recovery-drill`；该目标显式传入 `--isolated-only`，脚本仍会拒绝预生产和生产环境，并且只使用随机数据库、桶和 Redis DB 15。
