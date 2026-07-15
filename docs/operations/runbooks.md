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

恢复演练运行 `make recovery-drill`；该目标显式传入 `--isolated-only`，脚本仍会拒绝预生产和生产环境，并且只使用随机数据库、桶和 Redis DB 15。
