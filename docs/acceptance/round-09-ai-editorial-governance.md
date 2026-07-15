# Round 09 受控模型网关、审核治理与发布版本验收记录

- 日期：2026-07-15
- 用户场景：情报编辑对不可信网页/PDF 运行受控的分类、事实抽取、摘要和发布前复核，在三栏工作台逐项对照原文、字段、证据和摘要，再由职责分离的 reviewer 批准、拒绝、纠错或撤回；普通用户只能看到审核后 accepted claims 生成的摘要和不可变发布修订
- 发布与生命周期入口：唯一 `PublicationService`
- 模型执行边界：AI Worker 无工具、数据库写入、对象存储和发布权限

## 范围、复用与不做项

本轮交付模型网关、Mock/OpenAI 兼容 provider、四步任务、版本化运行记录、Prompt Injection 检测、严格 Schema/证据校验、review task/decision/revision 工作流、历史回放/影子结果/质量报告、canonical publication gate v2.1、发布路径清点、最小权限和三栏 ReviewWorkbench。

实现继续复用 `AppShell`、`IntelligenceFeedPage`、`TimelineFeed`、`IntelligenceCard`、冻结的 `FeedPage`/`ItemSummary`、唯一 `PublicationService`、`PdfEvidenceViewer`、`FactList`、`EvidenceDrawer` 和 `StatusBadge`。未创建平行卡片、查询服务、发布服务或新发布门禁。

本轮不做开放聊天机器人、模型自主工具调用、模型直接写数据库，也不开放生产自动发布。搜索全文、日报生成和通用缓存 API 仍留在后续轮次；本轮冻结其 revision/generation/visible 投影契约并完成撤回同步。

## 第一性原理与安全边界

1. 文档内容是不可信数据，不是指令。规则扫描命中“忽略之前指令、泄露密钥、调用工具、覆盖角色”等模式时提升为 R4 隔离；provider 请求永远不包含 tools/tool choice。
2. 模型输出只是候选。Pydantic 与官方步骤 JSON Schema 都拒绝额外字段、非法枚举和错误结构；事实抽取还验证 evidence_id 必须由服务端签发、定位块一致、摘录存在于规范化原文，claim/evidence 双向引用完整。
3. 发布授权来自服务端现查事实。来源等级、审核结果、风险、安全处置和发布建议即使出现在模型输出中也会被 Schema 或 v2.1 门禁拒绝，不能覆盖来源注册、当前文档、accepted claims、审核决定或安全扫描。
4. R3 必须人工审核、提交人与决定人分离且填写理由；R4 只能隔离，不能发布。事故安全原因、责任、法规效力和企业声明缺归因永远进入人审。
5. 发布修订是不可变快照。Prompt 或模型升级只能生成新的 pipeline run；历史回放和 shadow result 不会改写 `publication_revision`。

## 模型网关与版本化运行

`ControlledModelGateway` 统一接收 `ModelRequest`，执行本地 JSON 解码、Draft 2020-12 Schema、Pydantic 和证据锚点校验，再返回包含原始输出、校验后输出、Token、微美元成本、耗时和 provider request id 的 `ModelResponse`。OpenAI 兼容 provider 只发送 system/user message 与 strict JSON schema response format，并配置显式超时；Mock provider 用于 CI、fixture replay 和演示。

Alembic `0010_ai_editorial_governance` 新增 Prompt、Schema、模型档案、pipeline/step run、注入扫描、安全决定、内容审核决定、replay/shadow/quality report 及发布投影表。Prompt、Schema、模型、步骤输出、扫描、审核和评估事实由追加式触发器保护。

AI Worker 使用独立 `ai-worker` Compose 服务、`ai-model` 队列和 `SRBG_AI_*` 配置，只能调用被批准模型端点；环境中不含数据库或对象存储凭据。数据库 `srbg_model_role` 不再继承 runtime，且对 publication、publication_revision 和 Round09 治理表没有写权限。

## 唯一发布服务与投影同步

canonical `publication_gate.json`/evaluation schema 为 `2.1.0`；历史 v3-v7 文件仅用于旧版本回放。批准、拒绝、修订、重发和撤回 API 均调用既有 `PublicationService`。`scripts/audit_publication_paths.py` 清点 API 路由、后台动作、Worker、定时任务、管理脚本、迁移和直接 SQL，仅允许唯一 publisher repository 写 `publication`/`publication_revision`。

每个发布修订在同一数据库事务中更新 SEARCH、CACHE、DAILY_DIGEST 的 revision、visible 和 generation，并追加投影事件。publisher 队列仍通过 `PublicationService` 消费：缓存用 Redis 的 generation/visible 指针原子切换；搜索和日报读取数据库权威投影状态。撤回时三类 visible 同步变为 false，因此旧搜索项、缓存对象和日报引用不再可达，历史修订快照仍保留。

## UI 纵向切片

审核页新增三栏 `ReviewWorkbench`：左栏原文/PDF 证据，中栏候选字段与证据状态，右栏复用 `IntelligenceCard` 预览审核后发布卡；既有 `EvidenceDrawer` 继续承担证据细节。正式信息流和详情统一投影 AI 辅助/无 AI 降级、Prompt/Schema/模型版本、当前修订、重发和撤回状态。

`one_sentence_fact` 只有在四步 LIVE run 全部成功、摘要引用的 claim 全部为当前 item 的 accepted claims 时才进入 `ItemSummary`；否则只展示降级状态，不展示模型摘要。R3 未审核条目仍走服务端最小题录投影，R4 不返回浏览器。

## 回放、降级与对抗样本

`docs/codex-kit/assets/sample_items.json` 的 4 个样本和 `apps/api/tests/fixtures/round09/malicious_samples.json` 的 6 个恶意样本用于确定性 replay。质量报告输出 Schema 通过率、证据支持率、无证据扩写率、成本和 p95 时延；当前 Mock 报告为 Schema 100%、证据支持 100%、无证据扩写 0%、成本 0 microusd、p95 1 ms，6/6 恶意样本被拒绝。

模型故障将 pipeline 标记为 DEGRADED；信息流和详情保留题录与“无 AI 降级”，不会撤销或改写已发布 revision。对抗样本覆盖模型伪造“已审核”“高权威来源”“已解决安全风险”和应用/数据库直写发布表，均无法越过 v2.1 门禁。

## 迁移、回滚与验收结果

真实随机临时 PostgreSQL 已完成 `0009 → 0010 → 0009 → 0010`，并验证 publication 仅 publisher role 可写、AI Worker/应用/管理员直写同时失败。存在 Round09 治理记录、非内容审核任务或 R4 任务时，破坏性降级默认拒绝；生产回滚策略为停止 AI/publisher 队列、回退应用镜像并保留治理事实和发布快照。

最终门禁结果（2026-07-15）：

- `make round09-test`：41 passed；迁移回放、最小权限 RBAC、唯一发布路径审计通过。
- `make round09-eval`：4 个内容样本、6 个恶意样本；6/6 拒绝，质量指标通过。
- `make quality-gate`：通过；Python 417 passed / 8 skipped，UI 53 passed，Web 60 passed，契约 51 passed；Ruff、mypy strict、ESLint、TypeScript strict、设计令牌、可复现契约生成、pip-audit、pnpm high-level audit 和 Trivy HIGH/CRITICAL 均通过。pnpm 仅报告 1 个 low。
- `make fixture-replay`：155 passed，并输出 Round09 Mock 质量报告。
- `make web-e2e`：40 passed；当前 Web 生产镜像中的三栏工作台、逐字段安全审核、信息流和既有页面回归通过。
- `make web-a11y`：11 passed；审核工作台和既有关键路径 axe 扫描无违规。
- `git diff --check`：最终交付前通过。
