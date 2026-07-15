# 第12轮运行基线

## 基线身份

| 项 | 实测值 |
|---|---|
| UTC开始时间 | 2026-07-15T11:31:02.2647583Z |
| 分支 | `codex/round-10-feed-search-daily` |
| HEAD | `c9ffd4b2c70d3fa7a1c52fbb194dbba943039372` |
| 第11轮提交 | `c4f98eb0a4895021d0f1d28d8d278f54892bba1b` |
| 二阶段基线 | `9bd011f1c10719c69f923d6c5ad9fe7fd5d1eada`，见证提交 `c9ffd4b` |
| 初始工作树 | clean；tracked/cached diff均为空 |
| Docker | Client/Server 29.6.1，Docker Desktop 4.80.0 |
| PostgreSQL | 17.10 + pgvector 0.8.2 镜像 |
| Alembic | `0012_operations_readiness` |
| 环境等级 | TEST，本地身份与本地凭据；不是预生产/生产 |

## 容器与接口

API、Web、PostgreSQL、Redis、MinIO、ClamAV、Worker、Parser、Scheduler、AI Worker、Publisher、Prometheus、Alertmanager、Grafana 和 OTel Collector 均启动。运行探针：

- `/health/live` 200；
- `/health/ready` 200，PostgreSQL、Redis、对象存储均 up；
- `/api/v1/version` 200，`content_schema_version=1.1.0`、`search_schema_version=1.0.0`、语义搜索关闭；
- Redis故障注入时 readiness 降为 not_ready、liveness保持可用，恢复成功；
- 当前 TEST 环境无请求头也会获得默认本地身份，因此匿名HTTP 200不是生产匿名访问能力。预生产/生产拒绝本地身份由配置和OIDC测试证明，未在真实预生产验证。

## 首次数据库观察（运行测试前）

| 对象 | 估算行数 |
|---|---:|
| source | 158 |
| source_connector | 50 |
| source_checkpoint | 49 |
| fetch_run / fetch_record | 108 / 91 |
| document / document_version | 1524 / 1571 |
| intelligence_item | 46 |
| claim / claim_evidence | 367 / 367 |
| event / event_item / topic_cluster | 0 / 0 / 0 |
| publication / publication_revision | 37 / 81 |
| publication_projection_state / search_projection | 0 / 0 |
| daily_report / saved_item | 0 / 0 |
| audit_log | 2234 |
| usage_event | 250 |

这些是本地测试累积数据，不是生产规模或真实业务指标。专项测试会继续生成测试数据，因此所有计数均绑定上述时间点。

## 来源运行事实

- 46条仓库种子全部为 `CANDIDATE/disabled`。
- 首次数据库观察有54条 `ACTIVE/enabled`，其中49条名称为“固定测试来源”，5条为“集成测试来源”；没有非测试 ACTIVE 来源。
- 49条 ACTIVE 有 Fixture onboarding，连接器为 `MEM_SAFETY_REGULATION_FIXTURE` 或 `ROUND03_PDF_FIXTURE`；其余5条集成测试来源没有 connector。
- 108次 fetch_run 的 trigger 全为 `FIXTURE`，95成功、13部分成功，时间窗仅约7.5小时；不存在生产调度连续采集证据。

## 运行指标

- Operations API 可读，观察到13个 unhealthy sources、2个 publisher outbox 项；均来自测试环境。
- 100请求/并发10的负载测试错误0、P95 103.45ms；只证明当前本地测试数据下的API基线。
- 隔离逻辑恢复 RPO 0、RTO 0.11分钟；`pitr_production_evidence=false`。
- Alertmanager 测试路由仍未配置真实联系人；Sentry/OTel生产目的地未验证。

## 未核验

没有预生产/生产连接、真实OIDC、真实告警路由、生产PITR、连续14天窗口、真实来源时效或150来源容量数据。相关指标必须为null。

## 独立验收复测

- 复测开始：`2026-07-15T12:01:07.7527716Z`；入口HEAD `9a300cdfbb49141448d89f7bfc573373445f034e`；工作树clean。
- 静态和运行Alembic head均为`0012_operations_readiness`；API live/ready、完整版本响应、4个Celery节点和Web均通过。
- 100请求/并发10：错误0、P95 500.01ms；搜索40请求P95 31.72ms。两者均为TEST，不替代真实容量证据。
- 隔离恢复RPO 0、RTO 0.1分钟，`pitr_production_evidence=false`。
