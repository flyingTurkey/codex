# Owner 统一情报详情页 UI Prototype Handoff

> 状态：原型任务已完成，Owner 已于 2026-07-19 选择 B（正文主栏 + 上下文侧栏）。本文件保留为原型输入记录；正式规格输入见 `docs/srbg-intelligence-v2-owner-reader-to-spec-handoff-2026-07-19.md`，不要重新执行本原型任务或提升原型代码。

## 要回答的问题

> 面向单一 Owner 阅读的统一情报详情页，应该采用什么信息层级和布局，才能让高相关、有证据的内容最先被理解，同时不让诊断与纠正工具打断阅读？

本任务只制作可运行、可比较、可丢弃的 UI prototype，用来回答上述问题。不要修改正式 Nuxt 页面、业务契约、API、数据库或发布逻辑；prototype 不得成为生产依赖。保留有价值的是布局结论，不是原型代码。

## 开始前的权威材料

完整阅读并引用，不要复制或重新定义其中的领域决策：

- `AGENTS.md`
- `CONTEXT-MAP.md`
- `docs/contexts/publication-reader/CONTEXT.md`
- `docs/contexts/evidence-ai/CONTEXT.md`
- `docs/contexts/intelligence-qualification/CONTEXT.md`
- `docs/adr/0002-api-v2-empty-projection-cutover.md`
- `packages/contracts/src/srbg_contracts/models.py` 中的 `EventFullProjectionV2`、`EventMetadataProjectionV2`、`EventAppendixV2` 及其组成模型
- 当前正式页：`apps/web/app/pages/events/[id].vue`
- 现有浏览器验收：`apps/web/tests/e2e/intelligence-v2.spec.ts` 及其他 v2 reader/media E2E
- 设计权威：`docs/codex-kit/assets/ui/design_tokens.json`
- 视觉方向：`docs/codex-kit/assets/ui/references/selected-concept-01.png`
- 参考素材限制：`docs/codex-kit/assets/ui/references/README.md`

当前工作树另有 closeout/campaign 改动，不属于本任务。不要编辑、格式化、暂存或清理这些文件。

## 产品与使用场景

- 唯一用户是 Owner；页面首先是阅读页，不是企业审核工作台或证据调试器。
- 数字化转型、安全情报、行业热点复用同一详情契约和组件结构；只允许由 `PrimaryType`、facets、ClaimBasis 和内容状态形成增量差异。
- 页面入口是 Feed/Card、搜索和热点榜单；阅读完成后最重要的下一步是查看原文、下载允许的附件、理解证据边界，必要时才展开诊断或纠正。
- 原型应使用明确标注的静态 fixture，不得生成演示分数、伪造 AI 成功或把 fixture 接入正式页面。

## 已确认的普通阅读字段

### FULL 投影

这些内容必须可在不展开诊断附录的情况下被理解：

1. 标题。
2. 唯一主类型：`DIGITAL_TRANSFORMATION`、`SAFETY_INTELLIGENCE` 或 `INDUSTRY_UPDATE`。
3. 工程对象与专项 facets；它们是辅助定位，不应压过标题和正文。
4. 来源名称，以及“官方一手来源”状态。它与“已人工复核”必须分开表达。
5. 原文发布时间；缺失时显示“原文未提供”，不得推测。
6. 首次发现时间。
7. 原文摘录。
8. AI 总结及其状态。
9. ClaimBasis：厂商声明、研究结论、项目一手记录、独立验证或权威认定。它不是置信分数。
10. 原文链接。
11. 获准展示的图片。
12. 附件名称，以及允许时的下载入口；无再分发许可时只显示名称和原站链接。
13. 适用时的更正提示。
14. 适用时的热点触发路径、独立来源数和理由；普通阅读面不显示热点总分。

### R3 元数据投影

只能展示：标题、主类型、官方来源、原文发布时间、首次发现时间、原文链接和“待 Owner 审核”。不得在浏览器收到后再隐藏正文、claims、证据、媒体或 AI 内容。

### R4 与未投影内容

普通阅读路由返回 404，不设计“被遮挡的完整详情页”。R4 安全元数据只属于 Owner 隔离复核面，不在本阅读原型中假装可见。

## 证据与 AI 的不可跨越边界

- `SourceExcerpt` 是一段连续原文，最多 500 个中文字符，绑定 active AcceptedClaims 和证据定位；它不是摘要。
- `AISummary` 是 300–500 字的解释，结构为“发生了什么／工程影响与意义／限制与待跟踪”。事实段引用 AcceptedClaims，判断必须单独标识。
- AI 输出不是证据，不得比原文摘录获得更高的视觉权威；推荐以“原文摘录在前、AI 总结在后”的阅读顺序作为基线。
- AI 状态必须真实呈现：`NOT_GENERATED`、`PROCESSING`、`TEMPORARILY_UNAVAILABLE`、`SCHEMA_REJECTED`、`INSUFFICIENT_EVIDENCE`、`SUCCEEDED`、`STALE`。
- AI 未调用、失败、Schema 不合法或证据不足时，已通过证据门禁的内容仍然可读；状态区展示短原因和恢复预期，不展示伪造占位总结。
- 事故原因、责任、处罚结论及法规效力只有有权机关原文才能成为 AcceptedClaim。
- 厂商声明与独立验证不能合并成模糊“可信度”。
- 原文撤回、更正或版本变化时，更正提示应在阅读主区顶部可见；受影响 AI 总结显示 `STALE`，不能继续像有效总结一样呈现。

## 强制折叠到页面底部的 ReaderAppendix

默认折叠，且不得占据首屏主叙事：

- Accepted claims 明细与证据定位。
- 证据事实、原文段落/页码定位和处理诊断。
- 自动处理结果。
- 已审核事件关系与自动关系。
- 更正历史、版本关系和撤回记录。
- Owner 纠正与重新评估入口。

展开控件必须使用真实 button、`aria-expanded` 和可见焦点；按需请求 `GET /api/v2/events/{event_id}/appendix`。加载、失败、空附录和再次收起都要有原型状态。展开附录不应使主阅读位置意外跳动。

## 现有路由与资源边界

- 普通详情：`/events/{event_id}`。
- 详情数据：`GET /api/v2/events/{event_id}`，严格判别联合 `FULL | R3_METADATA`。
- 折叠附录：`GET /api/v2/events/{event_id}/appendix`，Owner 边界。
- 图片预览：`GET /api/v2/media/{media_id}/preview`，仅许可且安全派生的同源图片。
- 附件下载：`GET /api/v2/media/{media_id}/download`，扫描通过后 302 到最长 300 秒的私有签名地址。
- 原文链接是外部 HTTPS 链接，使用新窗口和 `noopener noreferrer`。
- Owner 复核入口当前为 `/review`；prototype 可以展示“去复核”的低优先级入口，但不能在阅读页重建完整复核工作台。
- saved/daily、引用和版本/diff 仍可能使用 `/api/v1`，但不应改变本次 v2 阅读信息层级。

## 原型需要比较的布局假设

至少制作两个使用同一 fixture、同一信息量的可切换方案；不得通过删字段让某方案显得更清爽。

### 假设 A：单列长文阅读

- 标题与来源元数据。
- 原文摘录。
- AI 总结及状态。
- 图片与附件。
- 原文动作。
- 页面底部折叠附录。

优势假设：移动端自然、阅读顺序明确。风险假设：桌面元数据和动作占用纵向空间，出处在长文中容易丢失。

### 假设 B：正文主栏 + 克制的上下文侧栏（推荐优先验证）

- 主栏承载标题、原文摘录、AI 总结、媒体和附件。
- 侧栏承载来源、两个时间、主类型/facets、ClaimBasis、原文链接和下载动作；只在宽屏适度 sticky。
- 更正提示跨主栏顶部；折叠附录仍位于全部阅读内容之后，不放进永久侧栏。
- 窄屏按语义顺序收敛为单列，不能把侧栏信息永久藏进抽屉。

优势假设：桌面阅读时来源与动作持续可见。风险假设：侧栏可能被误读为证据审核面，或压缩正文宽度。

可增加第三个方案，但不能用 Tabs 把“原文摘录”和“AI 总结”互相隐藏，因为二者的语义差异需要同时可比较。

## 需要覆盖的 prototype fixture

1. FULL、安全情报、官方来源、AI 成功、含一张许可图片和一个可下载附件。
2. FULL、数字化内容、`MANUFACTURER_CLAIM` 与 `INDEPENDENT_VERIFICATION` 并存，避免混淆。
3. FULL、行业热点，显示触发路径和理由但没有可见总分。
4. FULL、AI `TEMPORARILY_UNAVAILABLE`，原文摘录仍完整可读。
5. FULL、AI `STALE` 且有更正提示。
6. FULL、无图片、附件仅有原站链接。
7. R3 元数据投影。
8. 404/R4 不可见状态。
9. 附录加载、空、失败和有大量 claims/relations 的展开状态。

所有 fixture 必须显式标注为 prototype 数据，不得使用真实个人信息、真实密钥或未经许可的图片。

## 视觉与技术约束

- 方向：低饱和牛油果、高密度但克制、证据化情报卡；不能复制 AIHOT 品牌、Logo、独特图形，也不能把参考截图当背景或对外素材。
- 颜色、字体、间距、圆角、阴影和布局只取自 `design_tokens.json`。核心值包括 canvas `#F7F8F3`、surface `#FFFFFF`、reader max `1440px`、正文参考宽 `860px`、上下文/证据参考宽 `420px`。
- 字体使用 Noto Sans SC/Source Han Sans SC 等既有 font stack；正文 14–16px，阅读行高应接近 token 的 relaxed `1.75`。
- 语义状态使用既有 verified、reviewPending、vendorClaim、conflict 色；事故、更正和阻断不能使用品牌绿代替警示语义。
- 只使用 Iconoir；不要引入 React、第二套组件库或另一套正式前端技术栈。
- 正式实现若发生在后续任务，必须继续使用 Nuxt 4、Vue 3、TypeScript strict、Tailwind CSS 和 Nuxt UI 4；本 prototype 不得被正式页面 import。
- 支持 320px 起的响应式布局，重点检查 768、1024、1280、1440 和 1920 宽度；不得产生横向滚动。
- 必须有键盘可达顺序、清晰 `:focus-visible`、语义 heading 层级、图片 alt、状态文本而非只靠颜色、forced-colors 可读性和 `prefers-reduced-motion`。

## 决策评估标准

用任务而非审美投票评价方案：

1. Owner 能否在 10 秒内回答“发生了什么、来源是谁、原文何时发布、AI 是否可用”。
2. Owner 能否明确区分原文摘录、证据事实、ClaimBasis 和 AI 判断。
3. 主阅读路径是否在不展开附录时完整。
4. 原文、附件和复核入口是否容易找到但不会抢过正文。
5. AI 失败/R3/更正状态是否诚实、稳定且不造成空白页。
6. 桌面和移动端是否保持同一语义顺序。
7. 诊断附录是否默认安静，展开后又足够可操作和可追溯。

原型交付应包含：每个方案的可运行页面、桌面/移动截图、上述任务的观察记录、明确推荐方案及其取舍。不要只交付高保真静态图。

## 建议技能

1. 首先使用 `/prototype`：用 throwaway code 回答布局问题，不直接实现正式页面。
2. 使用 `/frontend-design` 或 `/design-an-interface` 生成和比较至少两个真正不同的信息层级方案；必须受本 handoff 与设计令牌约束。
3. 原型完成后使用 `/handoff` 把观察结论带回产品改造任务；只回传结论和证据，不把 prototype 代码接入生产。
4. 如果需要验证当前正式页的交互差异，可使用 `/e2e-testing`；不要因此修改正式测试或业务代码。

## 新任务建议首条指令

> 使用 `/prototype`，读取 `docs/codex-kit/prototype/owner-reader-detail/HANDOFF.md` 和其中引用的权威材料。制作至少两个使用同一组 fixture 的可运行 Owner 统一情报详情页方案，重点比较单列长文与“正文主栏 + 克制上下文侧栏”。不要修改正式 Nuxt 页面或业务代码；最终用任务观察推荐一个信息层级和布局。
