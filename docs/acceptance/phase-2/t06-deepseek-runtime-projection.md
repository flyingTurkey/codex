# T06 DeepSeek 运行、结果投影与自动补偿验收记录

## 票据与依赖

- 父 Spec：GitHub Issue #1。
- 本票：GitHub Issue #7。
- GitHub 原生 `blockedBy` 为 Issue #6；递归依赖链为 #6 → #5 → #2。实现开始前已逐票读取并确认三票均为 `CLOSED`。
- 实现前已完整读取根 `AGENTS.md`、父 Spec、本票、全部原生 blocker、`CONTEXT-MAP.md`，acquisition、intelligence-qualification、evidence-ai、publication-reader contexts，以及 ADR-0001/0002/0003。

## 纵向行为

1. 非测试环境只允许目录中的 DeepSeek provider。版本化服务端 profile `ai01-deepseek-deepseek-v4-flash-v1` 仅映射到固定公网模型 `deepseek-v4-flash`，不能提供运行时 endpoint、工具调用或任意模型名；CI 继续使用协议 stub。
2. `configured` 与 `available` 独立。可用性同时要求 Secret、当前激活配置、60 秒内 Worker heartbeat、健康队列、剩余预算、provider/model 一致，以及 24 小时内真实获准内容通过 T06 Schema 的成功事实。probe、canary、Secret 或 stub 不会写入该事实。
3. Worker 在读取原文前、每次物理调用前、回调解析后、模型内容写入前及成功事实落账时重新核验当前 SourceAdmission、Owner/来源运行意图、当前 DocumentVersion、raw CLEAN 与安全事实、TRIAL/PRODUCTION 执行域、DeepSeek 配置和预算。撤权回调只结算可验证 Token/费用；不进入内容解析、repair、候选或发布。
4. 摘要只消费当前 accepted claims 与连续 `SourceExcerpt`，并通过 `summarize-v2-output-1.0.0` 的 JSON Schema 和 Pydantic 双重校验。模型、prompt、文档、Schema、耗时、Token 和成本写入受限事实；原始/结构化模型结果不进入普通日志或普通 Reader。
5. `SourceExcerpt` 独立于模型成功保存。服务端投影固定七态：`NOT_GENERATED`、`PROCESSING`、`TEMPORARILY_UNAVAILABLE`、`SCHEMA_REJECTED`、`INSUFFICIENT_EVIDENCE`、`SUCCEEDED`、`STALE`，并提供七条唯一确定文案。AI 失败时，已通过 PublicationService 与 R3/R4 的来源和摘录仍可见。
6. 瞬时网络失败使用持久 5/15/45 分钟退避且两小时封顶；永久 Schema 拒绝不 retry/repair。摘要状态与刷新 outbox 唯一约束、PublicationService 决定幂等锁和现有候选/Event/claim 唯一约束共同防止重复。
7. AI Worker 无数据库、对象存储或发布权限；结果只经受控 callback 写受限事实，Reader 刷新只能由 `PublicationService` 消费耐久 outbox。R3 仍只有安全元数据，R4 仍只进入隔离区。

## TDD 与持久化证据

- RED：先观察到缺失 T06 availability/domain、迁移、摘要适配器、PublicationService handoff、七态文案和 UI 消费；随后分别锁住“撤权发生在原文读取前仍只结算费用”“永久 Schema 不重试”“版本化 profile 不能调用真实 provider”“每次物理调用前复核”和“刷新重放不重复发布决定”等失败。
- GREEN：以最小实现接入真实 DeepSeek adapter、权威重验、独立摘录、追加式真实成功/摘要状态、耐久刷新与 Publisher 补偿；未删除断言、降低门槛或增加 skip。
- `0041` 在一次性回环 PostgreSQL 完成 `0040 → 0041 → 0040 → 0041`，核验 prompt/Schema 注册、四张 T06 表、追加不可变触发器以及 Worker/Publisher 权限分离；资源由隔离 runner 清理。
- 本地只读检查确认 Compose AI Secret 文件存在，但没有读取或输出 Secret，也没有进行公网模型调用。该结果仅支持“Secret 文件已配置”这一单项事实。

## 非证据声明

本轮未生成或使用 Owner Gold，未调用真实 DeepSeek，未制造真实获准内容 Schema 成功，未执行或放宽任何真实 SourceAdmission，未启动采集运行窗口，也未形成 engineering/production GO。协议 stub、固定 canary、心跳、Secret、测试 source、一次性数据库和 UI fixture 都不得替代上述证据。PublicationService、R3/R4、robots、版权、条款、预算和公网安全边界均保持失败关闭。

## 门禁

- `t06-ai-runtime-test`：隔离迁移回放通过；Python 33 passed；Web 31 files / 94 tests passed。
- `lint`：Ruff、设计令牌及 UI/Web ESLint 通过。
- `typecheck`：mypy strict 146 source files、Vue/Nuxt/生成契约 TypeScript 检查通过。
- `test`：Python 1214 passed / 27 个仓库既有条件性 skipped；UI 53 passed；Web 94 passed。本票未新增 skip。
- `contract-test`：生成契约可复现，105 passed。
- `security-check`：pip-audit、pnpm production audit 和 Trivy HIGH/CRITICAL secret/misconfiguration 扫描通过。
- `fixture-replay`：356 passed；离线评估明确使用 mock，Schema/evidence support 为 100%，unsupported expansion 为 0，不构成 DeepSeek 成功。
- `quality-gate`：聚合复跑 lint、typecheck、test、contract-test 与 security-check，全部通过。
- `web-e2e`：63 passed；`web-a11y`：18 passed。浏览器 fixture 只验证七态文案消费与既有 R3/R4/证据优先界面，不构成真实内容或运行授权。
