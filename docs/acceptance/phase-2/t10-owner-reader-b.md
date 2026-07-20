# v2 T10 Owner Reader B 统一详情页验收记录

- Issue：`flyingTurkey/codex#11`
- Parent Spec：`flyingTurkey/codex#1`
- 日期：2026-07-20
- 状态：PASS（本票工程与浏览器门禁通过；不代表外部来源、DeepSeek 或 closeout GO）

## 前置与范围

GitHub 原生 `blockedBy` 已回读：#6（T05 PublicationService FULL/R3/404）和 #7（T06 DeepSeek 运行到结果投影）均为 `CLOSED`。#11 阻塞的 #12（ReaderAppendix）和 #13（媒体安全交付）仍为后续票，本轮只复用其现有投影和折叠入口，不提前实现治理附录状态机、签名下载服务或新的媒体后端。

本轮只改正式 Nuxt/Vue Reader：不改 PublicationService、发布状态、SourceAdmission、RuntimeAuthorization、robots、版权、公网安全或 closeout 规则，不引入 React、原型依赖或第二套组件库。

## TDD 证据

RED：先新增 `ReaderActions.test.ts` 和正式 Playwright 行为断言；首次运行因 `ReaderActions.vue` 不存在失败，测试文件 1 failed，既有 94 passed。未删除断言、降低门槛或增加 skip。

GREEN：最小实现单一 `ReaderActions` 与 B 布局后，Web 单元测试为 32 files / 95 tests 全通过，Nuxt strict typecheck 与 ESLint 通过。正式浏览器定向验收确认：

- FULL 同时显示来源官方性和独立人工复核状态、PrimaryType/facets、ClaimBasis、可空时间、热点理由但无总分；
- SourceExcerpt 在视觉与 DOM 阅读主线中先于 AISummary；事实段显示 AcceptedClaim ID，判断段明确标识“AI 判断”；
- NOT_GENERATED、PROCESSING、TEMPORARILY_UNAVAILABLE、SCHEMA_REJECTED、INSUFFICIENT_EVIDENCE、SUCCEEDED、STALE 七态逐一通过，STALE 同更正提醒关联；
- 单一 ReaderActions 只产生一个原文动作和每份材料的一个合法动作；无再分发许可材料只链接原站；
- 桌面 grid 计算为正文主栏与 sticky context/actions 侧栏，侧栏 `overflow-y: visible`，无嵌套滚动；移动几何顺序为 context、SourceExcerpt、AISummary、materials、actions、appendix；
- 320、640、768、1024、1280、1440、1920px 均无横向溢出；640px 作为 1280px 的 200% 等价阅读视口；
- 320px 下原文、原站材料、附录按钮的键盘顺序稳定，Owner Reader axe 无 serious/critical 问题。

## 边界声明

所有 FULL/R3/404 fixture 仅用于契约和页面行为回归，不是 Owner Gold、真实来源准入、真实采集运行窗口、DeepSeek `RealSchemaSuccess` 或任何 ENGINEERING/PRODUCTION GO 证据。本轮未联网调用 DeepSeek，未启用来源，未写发布状态，也未改变 R3/R4、robots、版权与公网安全失败关闭边界。

## 门禁结果

仓库内置 GNU Make 路径为 `.tools/make/tools/install/bin/make.exe`。最终结果：

- `make lint`：PASS（Ruff、tokens、UI/Web ESLint）；
- `make typecheck`：PASS（mypy 146 source files、UI vue-tsc、Nuxt typecheck、生成契约 tsc）；
- `make test`：PASS（Python 1217 passed / 27 个仓库既有条件性 skipped，本票未新增；UI 53 passed；Web 98 passed）；
- `make contract-test`：PASS（生成可重复；107 passed）；
- `make security-check`：PASS（pip-audit、pnpm audit、Trivy HIGH/CRITICAL、356 项安全回归）；
- `make fixture-replay`：PASS（356 passed，round09 mock 评估通过；不构成真实外部证据）；
- `make quality-gate`：PASS；
- 正式 Nuxt 生产镜像：PASS；
- `make web-e2e`：73 passed；
- `make web-a11y`：20 passed。

E2E 首轮还暴露并修复了两个可访问定位问题：R3 来源名不再在标题状态区与“来源上下文”重复；旧 Round10 搜索测试从模糊文本定位收紧为精确 Event 标题链接，不删除或弱化原断言。
