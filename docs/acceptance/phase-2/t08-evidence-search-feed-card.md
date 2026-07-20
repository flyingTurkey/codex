# T08 证据优先搜索与统一 Feed／Card 验收记录

## 范围与依赖

- GitHub Issue：`flyingTurkey/codex#9`，父 Spec `#1`。
- GitHub 原生 `blocked_by` 只有 `#6`（T05）与 `#7`（T06）；实施前二者均为 `CLOSED`。
- 适用领域：Evidence & AI、Publication & Reader Projection、Intelligence Qualification。
- 适用决策：ADR-0002 的 v2 空投影与 v1 不复活边界；ADR-0003 的工程／生产就绪隔离。
- 本票不新增数据库表或发布入口，只增量扩展 FULL 搜索响应与共享 Card；R3/R4、PublicationService、来源和运行授权边界不变。

## 验收行为

1. `PublicationService` 写搜索投影时，标题、来源、当前 AcceptedClaims 和 `SourceExcerpt` 使用 PostgreSQL A 权重，`AISummary` 使用 D 权重。
2. 连续中文短查询通过安全转义的子串匹配补充召回。证据文本子串命中增加 1,000,000 排名单位，AI 文本只增加 1,000；原 A/D `ts_rank` 继续参与稳定排序。
3. FULL 搜索结果的 `search_explanation` 只能列出 `TITLE`、`SOURCE`、`ACCEPTED_CLAIMS`、`SOURCE_EXCERPT`，并独立标记 `ai_summary_assisted`。至少存在一种真实命中来源；普通 Feed 与 Event Reader 不伪造搜索解释。
4. R3 搜索结果仍由 `EventMetadataProjectionV2` 精确白名单约束，不接收 `search_explanation`，也不返回 SourceExcerpt、AISummary、claims、证据、热点理由或媒体。R4 与未决内容继续在普通读取面失败关闭。
5. 首页、selected、all、digital、safety、industry、hot 与搜索结果继续复用同一 `IntelligenceFeedPage`、`TimelineFeed` 和 `IntelligenceCard`。卡片标题统一链接 `/events/{event_id}`，三个 PrimaryType 不创建第二套详情体验。
6. FULL Card 的原文摘录与 AI 总结／状态文案均限制为两行。AI 非成功时展示服务端确定状态，但已过 AcceptedClaims 门禁的原文摘录保持可读；R3 Card 不渲染 FULL 字段。
7. 搜索加载、空结果、Problem Details 错误、键盘顺序、200% 等效回流、屏幕阅读器状态和 axe 均由正式 Nuxt 浏览器故事覆盖。
8. 页面没有演示总结、演示评分、热点总分或模糊“可信度”聚合分。

## TDD 记录

- 契约红灯：FULL 拒绝 `search_explanation`；最小实现后 FULL 接受受控解释，R3 继续拒绝额外字段。
- 服务红灯：公开 `search()` 返回 FULL 但解释为空；最小实现只在 FULL 查询响应上附加数据库命中事实。
- Durable 红灯一：首屏 `cursor_rank=None` 导致 asyncpg 无法推断参数类型；显式 `bigint` 转换后通过。
- Durable 红灯二：`simple` 分词无法用“隧道”命中连续中文标题；增加安全转义的低成本子串召回后，“隧道／原文摘录／影响”均通过。
- Card 红灯：AI 非成功时原文摘录被隐藏，且没有状态或低权重 AI 说明；共享 Card 的 v2 可选视图模型修复后通过。
- 浏览器红灯：首次使用了会二次转换的旧 fixture，修正为正式 `FeedPageV2` 后验证真实页面；开发服务器随后暴露两个 strict TypeScript 可选值错误，完成类型收窄后通过。

## 自动化证据

- 定向契约／服务：`3 passed`。
- 当前单一 Alembic head 隔离回放及 durable FULL／R3 搜索故事：`18 passed`；短中文专项复跑：`1 passed`。
- Card 组件：`3 passed`。
- 正式浏览器搜索／R3／统一 Reader／axe 定向故事：`2 passed`。
- 全仓适用门禁结果在本轮最终验证后补记于下节。

## 全仓门禁

- `make`：当前 Windows 环境未安装 GNU Make，因此逐条执行 Makefile 中对应命令，未缩减子命令或断言。
- `lint`：通过（Ruff、design token 校验、UI/Web ESLint）。
- `typecheck`：通过（mypy strict 共 146 个源文件、UI/Web vue-tsc、生成类型 tsc）。
- `test`：通过（Python `1217 passed, 27 skipped`，既有 27 个条件性 skip 未变且本票未新增；UI `53 passed`；Web `98 passed`）。
- `contract-test`：通过，生成结果可复现，契约与跨层测试 `107 passed`。
- `fixture-replay`：通过，`356 passed`；round09 离线 adversarial fixture 评估 `passed: true`，provider 明确为 `mock`，成本为 0。
- `security-check`：通过；pip-audit 与 pnpm production audit 均无已知漏洞，Trivy secret/misconfiguration 扫描无 HIGH/CRITICAL 发现。
- `web-a11y`：通过，正式套件 `20 passed`；包含本票搜索解释、低权重 AI 标记和统一 Reader 跳转场景。
- `web-e2e`：已执行完整 73 项，当前混合脏工作区结果为 `64 passed, 9 failed`，因此本轮不宣称全仓门禁完成。失败集中在本票实施前已并行存在的首页／来源工作区改造：旧测试仍期待 `API v1 · Schema 1.1.0`，或期待现有页面已移除／禁用的来源添加和通知控件；4 个视觉用例由同一旧 API 文案断言失败。本票新增及相关的 v2 搜索、R3 白名单、统一 Feed/Card/Reader、键盘与回流用例全部通过。遵守范围约束，未修改这些无关页面或放宽其断言。

## 证据边界

- 所有 AI 文本、来源、准入和内容均为一次性协议 fixture。
- 未生成或使用 Owner Gold；未调用或宣称真实 DeepSeek Schema 成功；未形成真实来源准入、采集运行窗口、ENGINEERING_CLOSEOUT GO 或 PRODUCTION_CLOSEOUT GO。
- 未降低阈值、删除断言、增加 skip、吞异常或绕过 PublicationService、R3/R4、robots、版权、公网安全、预算与运行授权。
- 本票无数据库变更；回滚只需撤销搜索解释契约、查询和 Card 增量，不涉及数据降级。v2/v1 代际边界保持 ADR-0002 的不可逆语义。
