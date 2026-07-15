# Round 05 数字化转型案例验收记录

- 日期：2026-07-14
- 场景：政府/行业典型案例与企业自述案例的固定采集、结构化、审核、发布和展示
- 固定来源：交通运输部案例汇编、蜀道集团《智慧梁厂2.0》
- 发布入口：唯一 `PublicationService`，publication gate `5.0.0`

## 范围、复用与不做项

用户在 `/digital` 的同一情报信息流查看全国数字化案例，按工程专业、应用场景、成熟度和来源性质筛选，并切换全部/精选及最新/相关性排序。卡片与详情明确区分政府/行业案例源和企业自述，量化成效严格分为“发布方声称”与“独立证据支持”，每项成效可打开原始证据定位。审核员在既有审核页修改分类、场景、成熟度和成效归因；所有修改及发布仍由唯一 `PublicationService` 在同一事务中验证。

本轮复用 `AppShell`、`IntelligenceFeedPage`、`TimelineFeed`、`IntelligenceCard`、`FeedPage`、`ItemSummary`、`EvidenceDrawer` 和现有审核页，没有增加数字化专用卡片、平行查询服务或第二套发布链路。仅以 `DigitalCaseTypeSummary` 和 `DigitalCaseDetail` 增量扩展冻结契约。

本轮不做论文、产品型号库、语义聚类或真实 LLM；推荐动作仅为阅读原文、收藏、关注和技术调研，不输出采购结论。

## 第一性原理和证据边界

1. “领先、提升、节约、减人、提速”等结果属于发布者陈述，除非存在来源主体不同且明确标记为独立确认的证据，否则只能进入 `claimed_outcomes`。
2. 分类、实体关系、项目、成熟度、部署规模、适用性、复制条件、限制和风险必须来自当前版本的 accepted claim；客户端补丁不能创造新事实。
3. 单项目、多项目或企业规模应用必须同时具有命名项目和部署、运行或验收证据；缺少数量、时间或验收依据时 publication gate 默认拒绝规模成熟度。
4. 相关性只表示案例与四川路桥业务的匹配程度，不是可信度。v1 采用工程专业 70 分、四川实施 20 分、四川路桥直接关系 10 分，保存规则版本和分项 Claim 引用。
5. 企业案例可以自动进入“全部案例”的待审核投影，但始终显示“企业自述/厂商声明”；未经不同主体人工审核和严格门禁不能进入精选。
6. 两个生产来源种子保持 `CANDIDATE/disabled`；只有来源准入服务计算为 active 后才可采集，固定样本不授予生产访问权限。

## 数据、迁移与回滚

Alembic `0006_digital_cases` 新增：

- `digital_case_profile`：来源性质、成熟度、部署规模、适用性、复制条件、限制、风险和四川路桥关系；
- `digital_case_taxonomy`：工程专业、生命周期、技术标签和应用场景，逐项绑定 accepted claim；
- `digital_case_entity`、`digital_case_entity_relation`：企业、技术和项目实体及发布者、实施者、业主、供应商和应用关系；
- `digital_case_outcome`：量化/定性成效、发布方归因、Claim、证据及独立证据；
- `digital_case_relevance`：`relevance-v1.0.0` 总分、三项分值和因子 Claim。

迁移同时将数字案例加入既有内容类型/频道约束，允许 R1–R4 风险级别，并扩展同一文档中多主体/谓词 Claim 的唯一性。真实随机临时 PostgreSQL 已完成：

```text
0005_safety_case_lifecycle → 0006_digital_cases
0006_digital_cases → 0005_safety_case_lifecycle
0005_safety_case_lifecycle → 0006_digital_cases
```

空库实验室降级可用；存在 `DIGITAL_CASE` 数据时迁移主动拒绝降级。生产回滚采用停止 Round05 写入、回退应用镜像并保留事实表的策略。

## 固定样本与来源

`apps/api/tests/fixtures/round05/round05-digital-case-manifest.json` 仅保存必要短摘录、URL、页码、SHA-256 和预期规则结果，不在 Git 再分发完整 PDF：

| 来源性质 | 案例 | 核心门禁 |
|---|---|---|
| 政府案例 | 交通运输部案例汇编中的蒲江农村公路数字化案例 | 可在 active 来源、accepted claim、成熟度证据和完整发布门禁后进入精选；文中量化结果仍保留发布方归因 |
| 企业自述 | 蜀道集团《智慧梁厂2.0》 | 自动收录可进入全部列表但显示厂商声明；“减人50%、提速50%”不进入 verified，未经审核不进入精选 |

生产适配器复用统一 `SourceAdapter` 和注入式 HTTP 客户端，固定回放适配器完全离线；原始响应先进入既有私有文档库，再执行解析和 accepted-claim 投影。

## API、审核、UI 与指标

既有 `GET /api/v1/feed` 增加 `engineering_domain`、`scenario`、`maturity`、`source_nature` 和相关性排序；既有 `GET /api/v1/items/{id}` 增量返回 `digital_case` 详情。`POST /api/v1/admin/review-tasks/{id}/decisions` 仅在批准时接受 `digital_case_patch`，并在发布事务内校验受控词表、Claim、成熟度证据、实体归因和独立证据后重算相关性。

`/metrics` 增加按来源性质/成熟度的案例量、claimed/verified 成效量和企业案例待审核队列；publication gate 拒绝原因继续使用既有有界安全标签。结构化日志不记录正文、令牌或个人敏感信息。

前端采用现有低饱和牛油果、高密度时间线和证据卡样式。卡片展示成熟度、场景、来源性质、厂商声明、与四川路桥关系及可展开的相关性规则；详情展示实体关系、两组成效、适用性、复制条件、限制风险和允许动作；审核页支持分类、成熟度证据和归因修改。所有状态均有文字，不依赖颜色传意。

## 测试与演示证据

- Round05 定向测试覆盖契约、受控词表、成熟度、独立证据、相关性、双来源适配器、固定样本哈希、v5 门禁、事务审核、迁移回放和指标。
- Playwright 覆盖 `/digital` 筛选/排序、共享卡片、详情证据回跳、审核补丁和 axe；相关性区域明确显示 `relevance-v1.0.0`，页面不使用“可信度”。
- 新页面截图：[round-05-digital-cases-1440x900.png](assets/round-05-digital-cases-1440x900.png)。

最终门禁结果（2026-07-14）：

- `make quality-gate`：通过；Python 312 passed / 7 skipped，UI 53 passed，Web 48 passed，契约 42 passed；mypy、ESLint、契约再生成、pip-audit、pnpm high-level audit 与 Trivy HIGH/CRITICAL 均通过。
- `make fixture-replay`：90 passed。
- `make safety-case-test`：5 passed，确认 Round04 无回归。
- `make digital-case-test`：16 passed，并实际完成 `0005 → 0006 → 0005 → 0006` 迁移回放。
- `make web-e2e`：36 passed；`make web-a11y`：8 passed。
- `git diff --check`：通过。
