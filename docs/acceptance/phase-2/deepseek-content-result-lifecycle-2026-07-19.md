# DeepSeek 内容处理结果链路验收记录

日期：2026-07-19

## 症状与红色反馈环

真实 compose 数据库中有 10 条 durable content outbox 仍为 `WAITING_AI`，但关联 pipeline 已为 `FAILED/DEGRADED`，且没有成功模型步骤。诊断命令只读取 ID、枚举状态和计数，不读取 Secret、Cookie、正文或模型输入输出；同一命令连续两次均返回 `stuck_without_result=10` 并非零退出。

## 根因

1. API/Parser/Worker 运行镜像与工作树、Alembic 版本不一致；数据库仍为 `0033`，旧 Parser 缺少当前权威授权与 v2 状态投影。
2. pipeline 终态没有原子关闭 `source_content_outbox`，callback 到达前来源被人工停用时，输出被正确拒绝，但预算预留、失败步骤和 outbox 终态没有完整落库。
3. runtime probe callback 的预算 SQL 未显式标注 PostgreSQL timestamp 参数类型，随后又把内部 profile 版本串写成 catalog model，导致 Owner 投影长期停在 heartbeat stale/config mismatch。
4. 当前没有 `ADMIT + RUNNING` 来源，也没有 CLEAN 的当前 TRIAL 文档，因此真实内容调用应当被权威门禁拒绝；“Secret 已配置”本来就不等于“可以产生结果”。

## 修复与边界

- `0036_ai_content_result_lifecycle` 增加受限 `SECURITY DEFINER` finalizer，将成功、复核、降级和失败 pipeline 与 durable outbox 原子收口，并修复历史伪等待状态；Worker 仍无 outbox 直接 UPDATE 权限。
- callback 在读取任何步骤输入前重新核验授权；若授权已撤销，则不读取既有 AI 结果、不修复重试、不保存 provider 原始输出或 validated output，也不生成 claim、summary、Event 或投影。结构合法的已计费响应只保存 usage/cost/latency/request-id 计量元数据；畸形响应以未知用量结算并稳定记录 `AI_RUNTIME_AUTHORIZATION_DENIED`。
- runtime probe 显式 cast timestamp 并使用 catalog model 名。修复后 heartbeat 新鲜，Owner 投影准确返回 `CONFIGURED_UNAVAILABLE/NO_RECENT_REAL_SCHEMA_SUCCESS`。
- 未降低来源准入、运行态、当前文档、raw CLEAN、execution domain、预算、Schema、证据或 PublicationService 门禁；未启用来源、未伪造真实 Schema 成功。

## 验收证据

- 缺陷专项回归：`9 passed`。其中 PostgreSQL 用例使用 `SRBG_AI_LIFECYCLE_TEST_DATABASE_URL` 在事务回滚保护下真实调用 0036 finalizer，并断言 `WAITING_AI → DEAD_LETTER`；未提供该显式本机数据库变量时，该用例按设计跳过。AI 编排/网关/Worker/补偿/Owner 投影定向集：`56 passed`；Web Vitest：`92 passed`。
- 原始反馈命令修复后返回 `stuck_without_result=0`；Alembic 为 `0036_ai_content_result_lifecycle`。
- runtime probe 实际跨越 Scheduler、通用 Worker、隔离 AI Worker 和 callback，Redis `celery/ai` 队列均无积压。
- 当前权威门禁：`admitted_running_sources=0`、`trial_current_documents=0`。因此没有发起不合规的真实内容调用，`NO_RECENT_REAL_SCHEMA_SUCCESS` 保持为诚实限制。

## Code review

- Standards 轴发现授权复核晚于 SUMMARIZE/VERIFY 输入读取；已改为 `begin` 后立即复核，并用两个步骤的参数化回归证明撤权时不读取既有 AI 结果。
- Spec 轴发现畸形成功 callback 可能误入 repair，以及迁移测试仅静态断言；已分别增加永久拒绝回归和真实 PostgreSQL finalizer 状态转换回归。复审确认实现问题关闭。

## 已知限制

- 旧 callback 数据已经丢失，7 条历史 `RESERVED` 预算记录没有可信 provider usage，不能事后伪造结算；需单独设计账务对账/人工处置。
- 真实 DeepSeek 内容成功仍需一条经服务端准入的 RUNNING 来源和 CLEAN 当前 TRIAL/PRODUCTION 文档；本轮不为验收绕过这些门禁。
- engineering/production closeout 均继续为 `NO_GO`，尚缺真实 Schema 成功窗口、20 源、Feed、补偿与归档证据。
