# 运行手册执行入口

所有命令先确认目标环境，生产操作必须由值班人与业务责任人双人审批。

- `release`：运行全部 required checks，执行 Alembic upgrade，检查 readiness、错误预算与发布审计后逐步放量。
- `rollback`：停止 publisher/worker，回退应用镜像；保留 0012 运维事实，除隔离空库测试外不破坏性降级。
- `withdrawal`：审核员填写证据与理由，经唯一 PublicationService 撤回，验证 Feed、搜索、日报及缓存投影失效。
- `source_failure`：检查 DNS/TLS/HTTP/结构指纹；三次失败熔断，固定样本通过后影子采集并补采缺口。
- `model_anomaly`：停用异常模型/Prompt 版本，切回稳定版本，对受影响输入离线回放并进入差异审核。
- `redis_rebuild`：停 Worker，清空 Redis，从 PostgreSQL 未完成运行、Outbox、投影及 replay_request 重建后恢复 Worker。

恢复演练运行 `make recovery-drill`；该目标显式传入 `--isolated-only`，脚本仍会拒绝预生产和生产环境，并且只使用随机数据库、桶和 Redis DB 15。
