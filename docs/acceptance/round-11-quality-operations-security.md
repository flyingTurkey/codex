# Round 11 质量、运维、安全与上线门禁验收记录

- 日期：2026-07-15
- 执行环境：本地隔离 TEST Compose，不代表预生产或生产
- 工程切片结论：`PASSED`
- 生产就绪结论：`BLOCKED`
- 决策边界：本记录不写入、也不授权 `PRODUCTION_READY`；生产决定只能由独立有权验收人作出

## 用户场景、范围与复用

内部用户继续通过既有 `AppShell`、`IntelligenceFeedPage`、`IntelligenceCard` 和冻结的 `FeedPage`/`ItemSummary` 阅读、检索、收藏并反馈情报；管理员在同一应用壳查看来源健康、运行中心和质量看板，按权限发起失败任务重放。发布、撤回和投影仍只经过唯一 `PublicationService`，本轮没有创建平行信息流、卡片、发布服务或状态写入口。

本轮交付运维与安全纵向切片：Alembic `0012_operations_readiness`、运行/反馈/失败与重放事实，来源/队列/解析/AI/审核/API/搜索/成本指标，Prometheus/Grafana/Sentry/OpenTelemetry 基线，优先级失败队列与来源熔断观测，OIDC RS256/JWKS 校验，隔离恢复演练、负载基线、Runbook、环境隔离、CI required checks 和可审计 readiness 证据包。

不做项：不伪造 500/300/100/200/100 金标内容，不伪造连续 14 天运行或 20 名种子用户记录，不把本地逻辑恢复演练等同于生产 PITR，不用普通合并或修改候选报告绕过 required checks。

## 已实现并验证

- 指标与运行中心：`GET /api/v1/admin/operations/overview` 聚合来源健康/熔断、队列、失败任务、重放、审核、AI 失败/时延/成本/单文档成本；API 和搜索直方图由 Prometheus 客户端采集。
- 恢复控制：PostgreSQL 权威失败/重放队列以 `FOR UPDATE SKIP LOCKED` 按优先级领取；Redis 只作 Celery 传输。失败记录仅保存任务类型、执行标识、错误类别和安全重放标志，不保存正文、令牌、Cookie、模型输入、个人敏感 Payload 或其可关联哈希。来源发现、发布 Outbox 和投影支持人工重放；解析和 AI 失败尚缺可安全重建输入的专用适配器，因此保持安全失败。
- 观测栈：Prometheus 3.5.0、Alertmanager 0.28.1、Grafana 12.1.1、OTel Collector 0.133.0 均以固定版本运行；Prometheus API 目标实测为 `up`，5 条规则 health 为 `ok`，Grafana 数据库和 Prometheus 数据源正常。测试环境告警接收器故意为 `unconfigured`，生产联系人路由尚未验证。
- 身份与安全：预生产/生产只接受 HTTPS JWKS 的 RS256 OIDC，验证 issuer/audience/kid/exp/iat、UUIDv7 用户标识和角色；本地身份仅允许 demo/dev/test。指标端点只接受独立 bearer，不接受浏览器管理员角色。
- 数据保护：Compose 开启 PostgreSQL WAL archive/900 秒归档超时、私有且版本化对象桶；生产配置拒绝主存储与备份使用同一端点。隔离演练实际完成逻辑数据库、对象与 Redis 任务重建，RPO 0 分钟、RTO 0.1 分钟，但 `pitr_production_evidence=false`。
- UI：来源健康、运行中心、质量看板复用方案 1 令牌和 AppShell；反馈控件增量加入既有 IntelligenceCard。视觉回归、键盘、720px 的 200% 等效阅读视口和 axe 均通过。
- 隐私：SEARCH、VIEW_EVIDENCE、READ_DAILY、EXPORT 等被动使用事件只写入小时聚合桶，不含 actor_id 或 target_id，不形成默认服务端浏览历史；收藏、订阅、主动下载和显式反馈仅保留功能所需最小记录。
- 治理：工程 CI 校验 Schema、证据引用/哈希/commit/environment/window 一致性和“诚实报告 BLOCKED”，并成功退出；严格 golden/readiness 仍作为试点/生产晋级门禁。提供 CODEOWNERS 与分支保护示例及不可绕过说明，须由仓库管理员替换真实团队后启用。

## 原始证据与哈希

- readiness 证据包：[round-11-readiness-evidence.json](./round-11-readiness-evidence.json)，内含自校验 manifest SHA-256、策略 `quality_gates.json` v1.0.0 / SHA-256 `ff467b7e...fca`、金标 v1.0.0-seed / SHA-256 `9e5cc1ba...5433`、执行主体、时间和每项原始证据引用。
- 强制门禁汇总：[round11-quality-gates.json](./assets/round11-quality-gates.json)，SHA-256 `d12ed569f48d2ed872d4d7a248aef0a4efd774a8c708ff8bac9767e55d9eba66`。
- 安全扫描：[round11-security-scan.json](./assets/round11-security-scan.json)，SHA-256 `2a0564d0288f0541d52fbc76aaa003747410c947c9cac3f6d09e2a295e5c0454`。
- 观测运行实测：[round11-observability-runtime.json](./assets/round11-observability-runtime.json)，SHA-256 `3038ab8c7f0817861af001c4e86801894c9d6ca3da3393776e0574c033e0b0a6`。
- 当前窗口 SLO：[round11-slo-current-window.json](./assets/round11-slo-current-window.json)，SHA-256 `50839485339cdb86da5aeea788cb2536825381690316d4d4cba68c56fdc6d25c`；明确标记连续覆盖未验证。
- 恢复演练：[round11-recovery-drill.json](./assets/round11-recovery-drill.json)，SHA-256 `e8073898d5c007b23bc1bb16a4099e9d61fe33f70fe872177be6beea89659d09`。
- 负载基线：[round11-load-baseline.json](./assets/round11-load-baseline.json)，SHA-256 `20801f14fc3311e8670cefee6dff8352a1e6c3c549f4ce63a8043c853f900626`。
- 运维页面视觉证据：[round11-operations.png](../../apps/web/tests/e2e/visual-baselines/round11-operations.png)，SHA-256 `98c3c4fe71d796336c056404b22508097290fd6aedb4cd87edb5f1b150140edc`。

## 实际门禁结果

- `make lint`、`make typecheck`：通过；mypy strict 90 个源文件无问题。
- `make test`：Python 477 passed / 11 skipped，UI 53 passed，Web 69 passed。
- `make contract-test`：56 passed，生成契约可复现。
- `make security-check`：首次因 PyPI TLS/读取超时退出 2，未产生漏洞结论；原命令重试退出 0，pip-audit 无已知漏洞，pnpm 无 high/critical（1 low），Trivy secret/misconfig 无 HIGH/CRITICAL。
- `make fixture-replay`、`make quality-gate`：164 项固定/对抗测试通过；Prompt Injection 6/6 拒绝，无证据扩写率 0。
- `make round11-test`：41 passed，显式覆盖 OIDC 安全、发布路径和最小角色集成测试；迁移完成 `0011 → 0012 → 0011 → 0012` 实库回放；静态发布路径审计通过。
- `make observability-test`：6 passed；`make runbook-test`：2 passed。
- `make web-e2e`：42 passed；`make web-a11y`：13 passed。
- `make load-test`：最终证据运行 100 请求、并发 10、错误 0、P95 66.47 ms；成本为明确标记的 mock 0，不能作为生产模型成本。
- `make recovery-drill`：PostgreSQL/对象/Redis 恢复通过，隔离实测 RPO 0、RTO 0.11 分钟；不是生产 PITR 证据。
- 工程证据校验成功退出；严格 `make golden-replay` 与 `make readiness-evidence` 均因真实金标为空/生产证据不足而非零退出，确保不完整证据不能晋级生产。

## 阻断项

1. 版本化金标目录存在但真实数量均为 0，未达到 500 文档、300 重复对、100 事件、200 事实证据和 100 搜索问题；因此关键事实覆盖、误发布率和全部质量精度不能由规定金标证明。
2. 没有 20 名真实种子用户连续两周的验收与反馈记录，也没有连续 14 天来源/性能/SLO 监控窗口。
3. 尚无预生产/生产 PostgreSQL 基础备份 + WAL 到独立介质的完整 PITR 演练；当前仅证明隔离逻辑恢复，对象备份和 Redis 重建。
4. 生产 Alertmanager P0/P1 联系人、Sentry DSN/OTel 导出目的地尚未由运维密钥与真实路由验证。
5. AI 与解析失败队列尚缺以数据库权威输入引用重建的专用重放适配器；当前会安全失败，不会复用已哈希丢弃的敏感 payload。
6. CODEOWNERS 和分支保护仍是示例，需仓库管理员绑定真实团队并在托管平台启用后验证普通合并不可绕过。

因此本轮只能提交可审核框架和实测证据包，结论为 `BLOCKED`。
