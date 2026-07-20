# T04 证据化内容准备验收记录

## 票据与依赖

- 父 Spec：GitHub Issue #1。
- 本票：GitHub Issue #5。
- GitHub 原生 `blockedBy` 仅包含 Issue #2；实现开始前已确认 #2 为 `CLOSED`，关闭时间为 2026-07-19T15:24:45Z。
- 实现前已完整读取根 `AGENTS.md`、`CONTEXT-MAP.md`，以及 acquisition、intelligence-qualification、evidence-ai、publication-reader contexts 和 ADR-0001/0002/0003。

## 纵向行为

1. 输入仅来自当前文档版本中 active、已接受且存在当前证据定位的 claims；法规效力、事故原因、责任、处罚、整改等保留事实只接受有权机关原文证据。
2. `SourceExcerpt` 是单个证据块中的连续片段，最长 500 字，不拼接不相邻原文。每条候选保存 claim、evidence locator、文档版本和双向引用。
3. 结构化摘要可见正文为 300–500 字，并完整包含“发生了什么”“工程影响”“局限与后续”。事实段只能引用候选中的 current claims；判断段必须显式标为 AI 判断，不能携带 claim 引用。
4. 模型边界只实现协议等价 stub。调用前扫描 prompt injection 和敏感值；请求只披露 accepted claims 与证据摘录；响应先过 JSON Schema、再过 Pydantic，任一步失败均不落候选。
5. 候选与失效记录均为追加式 PostgreSQL 事实。文档版本变化、accepted claims 变化、来源撤回或更正分别产生稳定失效原因。Owner 复核投影分开呈现事实决定和 AI 摘要决定；未新增 Reader 页面或发布写路径。
6. `PublicationService` 仍是唯一发布入口；本票不更改来源准入、实际运行状态、R3/R4 投影、robots、版权或公网安全门槛。

## TDD 证据

- RED：内容候选、服务、仓储与迁移模块不存在时，新测试分别以导入失败进入红灯；prompt-injection、响应 Schema、字符计数防伪和 UUIDv7 持久化约束均先观察到定向失败。
- GREEN：最小实现后，T04 与受影响 v2 契约/服务定向套件共 44 项通过。
- 真实迁移：在一次性 PostgreSQL 数据库执行完整 `base -> 0039 head -> 0038 -> 0039`，空库降级与重放成功；一次性数据库随后强制清理。隔离运行器同时验证一次性 MinIO 桶创建与清理。

## 非证据声明

本次未使用私有 Owner Gold，未调用真实 DeepSeek，未执行或放宽来源准入，未开启采集运行窗口，也未生成 engineering/production GO。协议 stub、fixture、静态样例和本地迁移回放均不得作为上述事实的替代证据。

## 门禁

- `lint`：Ruff、设计令牌检查、UI/Web ESLint 全部通过。
- `typecheck`：mypy strict、UI/Web typecheck 与生成契约 TypeScript 检查全部通过。
- `test`：Python 1134 passed / 27 个仓库既有条件性 skipped；UI 53 passed；Web 92 passed。本票未新增 skip。
- `contract-test`：生成契约可复现，95 passed。
- `security-check`：`pip-audit` 与 `pnpm audit --prod --audit-level high` 无已知漏洞；Trivy HIGH/CRITICAL secret + misconfiguration 扫描通过。
- `fixture-replay`：Python 301 passed、Web 92 passed；固定评估的关键日期数字不支持数、未授权投影写入数和未验证 AI 主索引数均为 0。
- `quality-gate`：其组成门禁 lint、typecheck、test、contract-test、security-check 已逐项执行并通过。
- T04 定向回归：44 passed；未删除断言、降低阈值或新增 skip。
