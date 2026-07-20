# Issue #4：首页搜索优先入口验收记录

日期：2026-07-19；最终复验：2026-07-20

## 范围

本轮只交付正式 Nuxt 首页搜索的纵向行为：搜索区域先于“今日精选”一级标题和时间线出现，同时保持过滤 Feed 页面与既有搜索排序不变。未修改 API、搜索权重、PublicationService、R3/R4 投影、来源准入或运行授权。

## TDD 证据

1. 先将首页浏览器验收收紧为查找名为“搜索行业情报”的 `search` landmark；修改前失败，因为 landmark 没有屏幕阅读器名称。
2. 最小实现使用可见 label 作为 landmark 名称，并通过 Vue `useId` 为每个搜索实例生成唯一的 label/input 关联；原失败用例随后通过。
3. 再增加精确加载状态验收；修改前页面只暴露通用“正在加载安全情报”，无法准确描述搜索结果加载。共享 Feed 页面新增可配置 loading label，搜索页使用“正在加载搜索结果”。
4. 完整浏览器故事覆盖非空时间线 DOM/几何顺序、六个过滤页不重复首页搜索、空结果、Problem Details 错误、键盘焦点顺序、屏幕阅读器名称、640px 的 200% 等价回流和 axe。

测试未删除或降低既有断言，未新增 skip，未修改搜索排序算法。

## 安全与证据边界

- 浏览器数据全部是协议等价的确定性 fixture，只验证 UI 行为，不冒充真实 Feed、Owner Gold、来源准入、运行窗口或 DeepSeek Schema 成功。
- 本轮没有调用真实来源或模型，没有改变 `desired_enabled`、SourceAdmission、robots、版权、公网安全或预算状态。
- 本轮没有新增发布写路径；PublicationService 仍是唯一发布决策入口，R3/R4 服务端投影与 ACL 未改动。

## 验证结果

Windows 环境没有 `make`，以下均逐条执行 Makefile 中的等价底层命令：

- 本票 TDD 浏览器故事：`6 passed`。
- 全仓 Ruff、Web/UI lint、设计令牌检查：通过。
- mypy strict：149 个源文件通过；UI/Web typecheck 和生成契约 TypeScript 检查通过。
- 全量 Python：`1346 passed, 27 skipped`；UI：`53 passed`；Web：`101 passed`。本轮未新增 skip。
- 契约生成可重现；契约测试：`109 passed`。
- 安全检查：pip-audit 与 pnpm production audit 无已知漏洞；Trivy 无 HIGH/CRITICAL secret 或 misconfiguration。
- 当前正式 Nuxt 镜像构建并恢复健康；正式 Web E2E：`74 passed`；正式 Web a11y：`21 passed`，其中根首页 axe 违规数组为空。

Issue #4 的功能、回归、安全和前端门禁全部绿色，满足本票完成定义。GitHub Issue #4 已于 `2026-07-20T06:17:26Z` 关闭，并附最终门禁与证据边界评论。`fixture-replay` 不适用于这个纯前端切片，未运行；没有把其他票的 fixture、Owner Gold、来源或模型结果计作本票证据。

## 2026-07-20 工程基线 follow-up

在全新隔离 Compose 数据目录中只启动必要数据库/对象存储/安全扫描、API 与 Web 依赖，并显式禁用来源发现、外部搜索和真实 AI 后，Issue #4 再次通过正式 E2E `74 passed` 与 a11y `21 passed`。全量工程基线的映射、安全扫描、其他门禁和非 GO 边界见 `intelligence-v2-engineering-baseline-2026-07-20.md`；本次复验不 reopen、不重复关闭 Issue #4，也不改变任何来源运行状态。
