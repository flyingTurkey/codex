# T05 Reader 发布投影验收记录

## 票据与依赖

- 父 Spec：GitHub Issue #1。
- 本票：GitHub Issue #6。
- GitHub 原生 `blockedBy` 仅包含 Issue #5；实现开始前已确认 #5 为 `CLOSED`，关闭时间为 2026-07-19。
- 实现前已完整读取根 `AGENTS.md`、父 Spec、本票、Issue #5、`CONTEXT-MAP.md`，以及 acquisition、intelligence-qualification、evidence-ai、publication-reader contexts 和 ADR-0001/0002/0003。

## 纵向行为

1. 分类资格事实必须先于 Event Reader 投影；每个 Event 只有一个 `PrimaryType`。普通 `/api/v2` Reader 只消费 `PublicationService` 重建的 FULL 或 R3 投影，不从旧 v1 或候选表直接读取。
2. FULL 投影保存当前 title、三轴 facets、来源官方性、独立人工复核状态、两个可空时间、连续 `SourceExcerpt`、结构化 AI 摘要、`ClaimBasis`、热点原因、原文 URL、许可媒体、附件和证据附录。事实段 claim 引用必须属于当前 accepted claims；AI 判断保持独立语义。
3. R3 由严格契约限制为标题、主类型、官方来源、两个可空时间、原文链接和待审核状态等安全元数据。R4、未决、当前 claim/summary 不一致、原文不洁净或失效内容会删除旧物化投影并在普通 API 返回 404。
4. Owner-only R4 隔离端点只返回 case/event/version、风险级别、安全元数据、隔离原因和状态，不返回正文、摘录、claims、AI 摘要、媒体或附件。
5. Owner 复核继续使用追加式命令联合、`If-Match` 和幂等键；命令契约拒绝 publication status，事实决定和 AI 摘要决定彼此独立，最终重处理仍统一进入 `PublicationService`。
6. v2 代际保持空起步且不复活 v1 Reader。v1 归档使用对象存储汇总 SHA-256 和 PostgreSQL 逐行 SHA-256；0040 资格、发布决定和归档行均为追加式事实，有事实时拒绝破坏性降级。
7. 同一 Event 重建只保留一条当前物化投影；媒体与内容候选不因重试重复。Redis 只作为可丢弃缓存 seam，PostgreSQL 始终是业务权威，对象存储保持私有。
8. 发布结果使用仅含 `outcome` 的低基数计数器；原始对象不洁净或 claim/summary 与当前 accepted claims 失配会记为 `SAFETY_FAILURE` 并触发告警，正常 R3/R4 隔离不误报。

## TDD 与持久化证据

- RED：先新增 T05 严格 R3/FULL/R4 契约测试、Owner 隔离 API 测试、0040 迁移测试和持久化 seam；分别观察到缺失契约、404、缺失迁移及真实约束失败。
- GREEN：以最小实现补齐契约、PublicationService 重建、Owner 隔离读取和追加式事实；定向 T05 seam 最终为 16 passed。
- 真实迁移与存储 seam：一次性 PostgreSQL 执行完整 `base → 0039 → 0040 → 0039 → 0040`，Redis 验证可丢弃缓存，私有 MinIO 验证许可媒体和 v1 归档对象 SHA-256；隔离数据库和桶由 runner 清理。
- 测试数据使用明确 fixture source、协议 stub 与本地字节，不是获准真实来源或真实模型运行证据。

## 非证据声明

本次未生成或使用 Owner Gold，未调用真实 DeepSeek，未执行或放宽来源准入，未开启采集运行窗口，也未生成 engineering/production GO。测试 fixture、Redis 缓存、MinIO 对象和迁移回放均不得作为上述事实的替代证据；PublicationService、R3/R4、robots、版权和公网安全边界未被绕过。

## 门禁

- T05 定向持久化回归：16 passed；迁移回放通过；未删除断言、降低阈值或新增 skip。
- `lint`：Ruff、设计令牌检查、UI/Web ESLint 全部通过。
- `typecheck`：mypy strict（142 个 source files）、UI Vue typecheck、Nuxt typecheck 与生成契约 TypeScript 检查全部通过。
- `test`：Python 1141 passed / 27 个仓库既有条件性 skipped；UI 53 passed；Web 92 passed。本票的外部存储 seam 由独立目标显式执行，没有向默认套件增加 skip。
- `contract-test`：生成契约可复现，98 passed。
- `security-check`：`pip-audit` 与 `pnpm audit --prod --audit-level high` 无已知漏洞；Trivy HIGH/CRITICAL secret + misconfiguration 扫描通过。
- `fixture-replay`：355 passed；固定评估的 Schema 与 evidence support rate 为 100%，unsupported expansion rate 为 0。报告中的 mock 明确只是既有离线评估，不能作为 DeepSeek 成功证据。
- `quality-gate`：其组成门禁 lint、typecheck、test、contract-test、security-check 已聚合复跑并通过。
- `web-e2e`：63 passed；`web-a11y`：18 passed。这里验证可空时间兼容显示及既有正式页面边界，不构成真实内容或运行授权。
