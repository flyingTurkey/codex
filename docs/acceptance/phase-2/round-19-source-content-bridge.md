# 自动来源内容处理耐久桥验收记录

## 结论

本切片把自动来源生产采集形成的 `READY` 文档版本，可靠地送入现有 AI
治理事实中的待处理状态：

```text
SCHEDULED + PRODUCTION document_version READY
  → source_content_outbox(PENDING)
  → ID-only Celery task
  → ai_pipeline_run(LIVE, QUEUED)
  → source_content_outbox(WAITING_AI)
```

这是一条“已进入待处理队列”的耐久桥，不是自动内容发布功能。桥接事务不会创建
`claim`、`claim_evidence`、`review_task`、`publication` 或发布投影，也不会把模型候选
直接标为 `ACCEPTED`。现有 `PublicationService` 和默认拒绝发布门禁未被修改或绕过。

## 第一性原理与现有断点

不可再分的目标是：生产抓取成功后不能只停在文档库中，同时也不能因为追求自动化而
把尚未分类、抽取、核验或人工审核的内容直接发布。

代码审查确认了三个事实：

1. `source_runtime` 的生产文档登记只写 `document`、`document_version` 和版本
   `READY` 事件；它没有写内容处理 Outbox、`processing_run` 或 AI 运行。
2. 现有 `SafetyRegulationIngestionService` 是安全规定专用的“发现、再次抓取、解析、
   入候选”纵向链路，要求已有 `fetch_record_id`。自动来源生成的现成文档版本没有这项
   绑定，且内容可能属于数字化案例、论文、产品、安全案例等其他类型，不能强行套用
   安全规定解析器。
3. 现有 AI 层已经有严格的四步 Schema、无工具模型网关、`ai_pipeline_run` 和
   `ai_step_run` 事实，但尚无通用的生产编排器负责从任意 `READY` 文档组装最小输入、
   执行分类/抽取/摘要/核验并将候选送入各类型的服务端审核落库。发布门禁仍要求四步
   成功，而且摘要引用必须是当前条目的 accepted claims。

因此本轮最小正确边界是“可靠登记为 `LIVE + QUEUED` 后停止”。自动生成 UNKNOWN
条目、空 Claim、默认接受 Claim 或伪造审核任务，都会破坏证据约束，未被实现。

## 数据库与幂等

`0019_source_content_bridge` 新增独立 `source_content_outbox`：

- `document_version_id` 唯一，Celery 重复投递不能产生第二个业务交接；
- `READY` 事件触发器只接受 `SCHEDULED + PRODUCTION`、非 Fixture、非第17轮试点窗口
  的文档版本；迁移同时补录升级前已经存在的合格版本；
- 交接前重新核对当前文档版本、最新版本状态、生产 capture/run 以及原始对象 CLEAN
  安全事实；已被替换、隔离或拒绝的版本不能进入 AI 队列；
- `handoff_source_content_to_ai` 在同一数据库事务中创建 `ai_pipeline_run(QUEUED)` 并把
  Outbox 标为 `WAITING_AI`。任务在提交前后宕机都不会留下半条交接；
- 失败只保存受控 reason code，最多5次并有有界退避，之后进入 `DEAD_LETTER`；失败任务
  和人工优先重放都只保存/重投 `outbox_id`，不保存 URL、正文、查询词、模型输入或密钥；
- Worker 对新表没有直接读写权限，只能执行三个窄 `SECURITY DEFINER` 命令。API 只读
  权限仅用于运维重放时重新验证权威状态。

存在任何 Outbox 事实时，数据库降级以 `ROUND19_DOWNGRADE_BLOCKED` 拒绝删除耐久交接；
应优先应用回滚并向前修复。

## 发布隔离

桥接 Worker 没有导入或实例化 `PublicationService`，数据库命令也没有 Claim、Evidence、
Review 或 Publication 写语句。后续 AI 编排即使完成，仍必须经过以下既有链路：

```text
模型候选（无权威）
  → 服务端 Schema/证据锚校验
  → 类型专用候选持久化
  → accepted claims + 双向 evidence
  → R3/R4 服务端投影和职责分离人工审核
  → PublicationService 默认拒绝门禁
  → 搜索/缓存/日报/Feed 投影
```

`WAITING_AI` 不等于 `READY_FOR_REVIEW`，更不等于 `PUBLISHED`。在通用生产 AI 编排器交付
前，这些记录会诚实地保留在待 AI 队列，不会进入普通用户 Feed。

## 测试证据

- `apps/worker/tests/test_source_content_bridge.py`：ID-only 任务、并发/重放幂等、受控失败
  原因、窄数据库命令及禁止发布/Claim 写依赖；
- `apps/api/tests/test_source_task_replays.py`：失败记录只保留 Outbox ID，重放前重新读取
  Outbox 状态，`WAITING_AI` 安全转为终态 no-op；
- `apps/api/tests/test_round19_source_content_bridge_migration.py`：单一迁移 head、生产 READY
  触发/补录、证据重校验、最多5次重试、Worker execute-only 和降级保护；
- `apps/api/tests/test_ai_pipeline_runtime.py` 与 `test_publication_gate.py`：继续验证模型输出
  的 Schema/证据边界和发布门禁，没有因桥接放宽。

## 最终验收结果（2026-07-17）

桥接专项测试为24通过；迁移静态测试为55通过、2跳过；Worker 相关测试为67通过、1跳过。
真实 PostgreSQL 验证了 `READY → PENDING → LIVE/QUEUED → WAITING_AI`，重复交接后仍只有
一个 pipeline run，且 Claim、Evidence、Review 和 Publication 均为0。根级全量门禁结果
记录于第18轮总体验收，当前数据库 head 为 `0019_source_content_bridge`。

## 0018/0019 基线收口复验（2026-07-17）

`2026-07-17 09:53:05 +08:00` 的本次新复验使用一次性真实 PostgreSQL，从0017c连续升级
到0018、0019并确认唯一 head 为 `0019_source_content_bridge`。集成回归结果为
`1 passed in 5.64s`，同时证明 Worker 不能直接读写内容 Outbox、只能执行窄
`SECURITY DEFINER` 接口；存在 Outbox 时受保护降级明确返回
`ROUND19_DOWNGRADE_BLOCKED`。

生产 `READY` 文档的唯一自动结果仍是：

```text
source_content_outbox(PENDING)
  → ai_pipeline_run(LIVE, QUEUED)
  → document_version(WAITING_AI)
```

首次交接报告已排队，重复交接返回相同 pipeline id 且不再排队；pipeline 与 attempt 均只有
一条。交接前后的 Claim、Claim Evidence、Review Task、Publication Revision 和发布投影计数
完全不变，没有调用 `PublicationService`，没有执行任何真实模型请求。

本次根级命令全部退出0：`make lint`、`make typecheck`、`make test`、
`make contract-test`、`make security-check`、`make fixture-replay`、`make quality-gate`、
`make web-e2e`、`make web-a11y`。新计数为 Python 1198通过/30跳过、UI 53通过、Web 106通过、
契约86通过、Fixture 352通过、E2E 47通过、a11y 15通过；Trivy high/critical 密钥与错误配置
均为0。Compose 完整健康周期内主 Worker 已为 healthy，运行容器仍以 `mock` provider、空 AI
key 工作，发现、资格和百度均默认关闭。
