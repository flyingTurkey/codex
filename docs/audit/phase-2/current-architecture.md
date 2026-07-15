# 第12轮当前架构审计

- 审计提交：`c9ffd4b2c70d3fa7a1c52fbb194dbba943039372`
- 首次运行观察：2026-07-15 11:31:02 UTC
- 环境：本地 TEST Compose，不代表预生产或生产
- Alembic：脚本与 owner 查询均为 `0012_operations_readiness`

## 证据等级

| 等级 | 含义 |
|---|---|
| E1 | 代码、迁移、配置和契约静态证据 |
| E2 | 确定性测试、Mock 或 Fixture 回放 |
| E3 | 当前数据库、容器、API 和低权限登录实测 |
| E4 | 获批真实来源、连续运行、真人金标或生产外部证据 |

方案、README、CHANGELOG 和历史验收只能说明设计或历史声明，不能单独证明能力。

## 实际运行拓扑

```text
Nuxt Web
  -> FastAPI /api/v1（当前 TEST 环境默认本地身份）
     -> PostgreSQL 17.10（业务事实与当前 Item 发布读模型）
     -> Redis 7.4（Celery、缓存）
     -> MinIO（私有原始对象）

Celery Beat / scheduler
  -> 每15分钟固定调用 srbg.safety_regulations.discover
  -> MEM 安全规定专用 runner
  -> 当前数据库连接器全部为 Fixture 类型

Worker / parser / ai-worker / publisher
  -> parser/worker 使用 srbg_worker_login
  -> API 使用 srbg_api_login，另持有 publisher 专用连接
  -> publisher 使用 srbg_publisher_login
  -> ai-worker 默认 provider=mock
```

静态 Beat 证据见 `apps/worker/src/srbg_worker/app.py:37-62`、`apps/worker/src/srbg_worker/app.py:106-108`。唯一周期来源任务是 MEM 安全规定；其他数字案例、论文和产品适配器虽实现 `SourceAdapter` 形状，但没有注册到统一动态调度链。

## 对象现状与二阶段适配性

| 对象 | 当前事实 | 判断 |
|---|---|---|
| `document` / `document_version` / `raw_object` | 原始响应、版本与对象引用已存在；首次观察有1524/1571条文档/版本测试数据 | 可扩展，但须加入保留/删除执行事实 |
| `claim` / `claim_evidence` | Item-keyed；367条 Claim 与367条 Evidence；定位字段完整 | 可迁移到 Event 发布输入，需保持历史 Item 关联或桥接 |
| `event` / `event_item` | 表存在但当前均为0；事件偏安全案例，未成为门户身份 | PARTIAL；语义与二阶段“唯一用户身份”冲突 |
| `topic_cluster` | 表存在、当前0；通过 `topic_cluster_event` 连接 Event | 结构可扩展，缺真实使用和稳定 Event 前置 |
| `publication` / `publication_revision` | 37/81条；均以 `item_id` 为主键，revision snapshot 可复用 | 需 event-keyed 影子投影，不能直接原地切换消费者 |
| `publication_projection_state` | 表存在但当前0；只记录 SEARCH/CACHE/DAILY_DIGEST 状态，不是普通用户专用行投影 | 语义冲突；不能充当二阶段只读发布投影 |
| `search_projection` | `item_id` 主键，包含 `risk_level`；当前0 | 索引结构可扩展，身份和风险字段需迁移 |
| `daily_report_item` | 固定 `item_id + publication_revision_id` 快照 | 快照语义可复用，身份需一次性转为 Event |
| `saved_item` / collection | `owner_id + item_id` | 用户隔离可复用，需不可变 Item→Event 映射回填 |
| Feed / Item detail | 当前直接查询业务表和 publication，并允许 R3 白名单 Item | 不是专用只读投影；第13轮首要差距 |

## Item 与 Event 迁移约束

当前 Feed、详情、收藏、日报、搜索、引用与 publication revision 都把 Item ID 当作公开稳定身份；Event API 只是附加能力。迁移必须：

1. 先建立 event-keyed、revisioned 影子发布投影及真实只读角色，不切消费者；
2. 建立不可变 `item_id -> event_id` 映射并验证每个已发布、日报、收藏、搜索和引用对象恰有一个目标；
3. 同一切换窗口把 Feed、搜索、日报、收藏、详情和下载改为 Event；
4. Item 页面使用308，API返回 Deprecation/Link，Sunset 未获确认时不删除；
5. revision ID 保持不变或提供不可变 revision 映射，历史日报不得重写。

## 150来源风险

- 调度：静态 Beat 只会触发一个 MEM runner，没有 PostgreSQL 到期计划、租约或来源预算，无法承载150来源动态治理。
- 队列：按 parser/publisher/ai 粗粒度分队列，缺来源级公平、动态并发和完整安全重放；解析/AI仍可能 NON_REPLAYABLE。
- 索引：PostgreSQL pg_trgm/FTS/pgvector 足以继续试点，但当前搜索投影为空，尚无150来源真实体量、更新和撤回压力证据。
- 缓存：generation/visible 机制有测试，当前投影状态为空；未证明高频修订、Redis丢失后的全量重建时间。
- 文件：有大小、MIME、页数、解压炸弹和ClamAV控制，但没有150来源文件分布、OCR峰值和对象保留成本。
- 模块边界：`safety_regulations/query.py` 已聚合多内容类型、AI、事件、产品和发布查询，达到150来源前应在不拆微服务的前提下收紧读投影边界。

## 结论

模块化单体、证据链、版本、唯一 `PublicationService` 和基本运维设施可以继续扩展；动态来源治理、Event唯一身份、专用普通用户发布投影和真实低权限读取尚未成立。建议第13轮先完成影子投影与数据库隔离，第14轮再统一切换 Event。
