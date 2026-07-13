# 第 09 轮：AI 流水线、审核与发布门禁

```text
执行第09轮：接入受控模型网关，实现分类、事实、摘要、复核和发布版本。

读取：docs/codex-kit/docs/05-ai-pipeline.md、docs/codex-kit/docs/08-security-threat-model.md、docs/codex-kit/assets/content.schema.json、docs/codex-kit/assets/schemas/classify-output.schema.json、docs/codex-kit/assets/schemas/extract-output.schema.json、docs/codex-kit/assets/schemas/summarize-output.schema.json、docs/codex-kit/assets/schemas/verify-output.schema.json、docs/codex-kit/assets/prompts/全部文件、docs/codex-kit/assets/validation/publication_gate.json、docs/codex-kit/assets/validation/publication_evaluation.schema.json。

必须交付：
- 模型网关接口、Mock provider和至少一个可配置OpenAI兼容provider；
- Prompt、Schema、模型、参数、输入哈希、输出、成本和耗时版本化；
- 分类、事实抽取、摘要、发布前复核四步任务；
- Pydantic/JSON Schema拒绝额外字段、非法枚举和无证据关键事实；
- Prompt Injection检测和AI Worker无工具/数据库写权限的架构保证；
- 扩展第02轮已有的唯一 `PublicationService` 和 `publication_gate.json` v2，不得另建平行发布入口或用新门禁替换它；
- 清点 API 路由、后台动作、Worker、定时任务、管理脚本、数据迁移和直接 SQL 中的全部旧发布路径，迁移到 `PublicationService` 或删除；任一绕过路径都是本轮阻断项；
- 保留数据库最小权限：仅发布服务角色可写 `publication` 和 `publication_revision`，其他应用角色、AI Worker和人类管理员都不得直写；
- 规则门禁仅信任服务端现查数据和有权审核决定；AI输出的来源等级、评分、审核状态、风险级别、安全处置或发布建议均是无授权性候选字段，不得决定发布；
- review_task、decision、publication_revision完整工作流；
- 审核原文/字段/证据/摘要对照，批准、拒绝、纠错、撤回；
- R3/R4强制人审、职责分离和理由；
- 历史回放、影子运行和质量报告；
- 模型故障降级为题录并保留已发布快照。

测试：
- 文档内“忽略指令/泄露密钥”不改变系统输出；
- 模型多写字段、错误JSON、伪造evidence_id均被拒绝；
- 无证据关键事实无法发布；
- 企业声明缺归因进入人审；
- 安全原因、责任、法规效力永远强制人审；
- 模型升级不会静默改写已发布内容；
- 撤回同步刷新搜索、缓存和日报引用。
- 所有公开、精选、修订、撤回和重发端点都通过 `PublicationService`，绕过服务的直接写入在应用层和数据库层同时失败；

验收：用 docs/codex-kit/assets/sample_items.json 和恶意固定样本完成 fixture-replay；quality-gate 输出 Schema 通过、证据支持、无证据扩写、成本和时延；用“模型伪造已审核/高权威来源/已解决安全风险”和“直写发布表”对抗样本确认不能绕过 v2 门禁。

不做：开放聊天机器人、模型自主工具调用、模型直接写数据库。
```
