# Round 08 去重、事件聚类、热点和评分验收记录

- 日期：2026-07-15
- 用户场景：情报编辑在四类既有内容闭环中识别重复、转载和事件关系，比较独立信源，在热点与事件时间线中查看可解释评分，并由 reviewer 人工合并、拆分或确认关系
- 评估状态：`INTERNAL_TEST_FIXTURE`，`human_adjudicated=false`，`auto_merge_enabled=false`
- 发布与人工决定入口：唯一 `PublicationService`

## 范围、复用与不做项

本轮交付精确去重、近似重复候选、规则/可选向量召回、转载和镜像谱系、独立信源计数、跨内容域事件、主题聚类、关系工作台、八维评分、热点、事件来源对比、内部评测夹具和离线评测命令。

实现继续复用 `AppShell`、`IntelligenceFeedPage`、`TimelineFeed`、`IntelligenceCard`、冻结的 `FeedPage`/`ItemSummary`、既有事件时间线和唯一 `PublicationService`。评分只增量扩展 `ItemSummary.scores`；卡片最多显示一个“相关度”按钮，抽屉展示当前可用的相关性、权威、影响、新颖、时效、证据、置信和热度分项、特征解释、规则版本、原始分及人工覆盖理由。

本轮不做黑盒个性化推荐、图数据库或大规模向量服务。pgvector 仅是可选候选召回器，默认关闭；无论候选来自规则还是向量，硬约束均在合并前再次执行。

## 第一性原理与硬约束

1. 精确身份优先于文本相似：规范 URL、外部 ID、DOI、机构域内文号和 SHA-256 哈希分别形成可追溯身份键。
2. 文本相似只能产生候选。标题、正文指纹、实体、时间和地区用于规则召回；可选 pgvector 结果与规则结果取并集，但不同项目、标段、型号、文号或事故阶段必须阻断合并。
3. 修订、澄清、撤回、更正和后续材料表达的是时间关系，不是可删除重复项；同 URL 内容哈希变化形成内容更新关系。
4. 来源数量按独立来源主体计算。同一通稿转载和同机构镜像保留谱系，但不会增加独立信源计数。
5. 八个分项独立计算。热度仅表达关注变化，不进入置信分；缺少 accepted claims 或证据时不生成演示分数。
6. 人工决定必须填写理由，由 reviewer/platform_admin 经唯一 `PublicationService` 锁定候选、执行硬约束、追加决定/审计，并写入 `resolution_regression_sample`。

## 数据、迁移与回滚

Alembic `0009_dedup_events_scoring` 新增：

- `item_identity_key`、`document_fingerprint`：精确身份与近似指纹；
- `duplicate_candidate`、`duplicate_decision`、`duplicate_link`：只推荐候选、人工决定和正式重复链接；
- `source_affiliation`、`source_lineage`：来源主体、转载和镜像谱系；
- `topic_cluster`、`topic_cluster_event`、`cluster_decision`：主题成员和人工合并/拆分审计；
- `score_set`、`score_dimension`、`score_override`：版本化规则分项、原始分和追加式人工覆盖；
- `resolution_regression_sample`：人工决定自动形成回归样本。

事件类型扩展为 `SAFETY_INCIDENT`、`REGULATION_CHANGE`、`DIGITAL_PROJECT`、`RESEARCH_RESULT` 和 `PRODUCT_RELEASE`；非安全事件不伪造事故阶段或状态。既有 `digital_case_relevance` 迁移为通用相关性分项，但保留原始规则版本。

真实随机临时 PostgreSQL 已完成 `0008 → 0009 → 0008 → 0009`。存在人工决定或非安全事件时降级默认拒绝；生产回滚策略为停止 Round08 写入、回退应用镜像并保留人工决定和评分事实。

## API、UI、权限与观测

新增只读接口：

- `GET /api/v1/hot-topics`：仅投影已确认主题和已发布事件，明确返回自动合并关闭状态；
- `GET /api/v1/events/{id}/source-comparison`：展示来源主体、转载/镜像角色和独立来源数；
- `GET /api/v1/admin/clustering-workbench`：reviewer 可读的重复、事件、主题和关系候选。

新增写接口 `POST /api/v1/admin/clustering-workbench/{kind}/{id}/decisions` 与 `POST /api/v1/admin/items/{id}/score-overrides`。请求 Schema `extra=forbid`，不能夹带发布状态；动作按候选类型白名单约束，关系确认必须携带候选关系类型，重复硬冲突不能合并。

UI 在同一壳层新增 `/hot` 和 `/admin/clusters`，事件详情复用原时间线并增加来源对比。R3/R4、未发布项和评分投影继续由服务端控制，不依赖浏览器隐藏。`/metrics` 增加待处理重复/主题、硬约束阻断、向量候选、已评分项、人工覆盖及合并/拆分计数。

## 内部金标结构与离线评测

`apps/api/tests/fixtures/round08/` 包含 300 对重复/非重复和 100 个事件簇结构，清单保存数量、SHA-256、评估标签和自动合并开关。`scripts/evaluate_round08.py` 输出重复精确率、召回率和聚类纯度。

当前确定性内部夹具结果为：精确率 100%、召回率 100%、聚类纯度 100%。由于 `human_adjudicated=false`，这些数字只能证明评测管线和回归结构可运行，不能证明生产指标达到 98%/93%/95% 门槛，因此产品状态保持“内测评估”，所有近似结果只能推荐候选，自动合并固定关闭。

## 安全复核

所有新 SQL 使用参数化查询；URL/关系类型/分值/理由均受 Pydantic 类型与长度约束。人工决定端点只允许 reviewer/platform_admin，运行角色只能写候选和原始评分，不能写决定、覆盖或发布状态。追加式触发器保护决定和审计，来源谱系不暴露正文、令牌或个人敏感信息。安全扫描未发现 HIGH/CRITICAL 密钥或配置问题，依赖扫描只有 pnpm 已知 1 个 low。

## 验收结果

最终门禁结果（2026-07-15）：

- `make round08-test`：14 passed；随机临时 PostgreSQL 完成 `0008 → 0009 → 0008 → 0009`，最小权限 RBAC 集成通过。
- `make round08-eval`：300 对、100 事件；内部夹具精确率 100%、召回率 100%、聚类纯度 100%，自动合并关闭。
- `make quality-gate`：通过；Python 381 passed / 8 skipped，UI 53 passed，Web 57 passed，契约 51 passed；Ruff、mypy strict、ESLint、TypeScript strict、可复现契约生成、pip-audit、pnpm high-level audit 和 Trivy HIGH/CRITICAL 均通过。
- `make fixture-replay`：134 passed，覆盖规则召回、硬约束、八维评分和唯一发布服务。
- `make web-e2e`：40 passed；热点、评分抽屉、关系工作台及既有页面回归通过。
- `make web-a11y`：11 passed；热点和工作台 axe 扫描无违规。
- `git diff --check`：最终交付前通过。

## 下一轮起点

生产自动合并仍关闭。下一步必须由领域专家人工裁定并版本化更大规模金标，覆盖真实边界样本、来源偏差和跨地区/跨阶段事件；只有独立评测达到精确率 ≥98%、召回率 ≥93%、聚类纯度 ≥95%，并完成影子运行和误合并审查后，才能另行评估是否开放受控自动化。
