# Handoff：Owner Reader 统一情报详情页 to-spec 输入

日期：2026-07-19
状态：`to-spec=READY`
已确认方案：B（正文主栏 + 上下文侧栏）

## 1. 要回答的问题与最终答案

面向 Owner 阅读的统一情报详情页采用“证据优先的正文主栏 + 受约束的 sticky 上下文侧栏 + 页面底部默认折叠附录”。宽屏双栏，窄屏按同一语义顺序收为单列。原文摘录的视觉权威高于 AI 总结；来源官方性与人工复核状态并列但不合并；诊断和纠正能力不占据主要阅读路径。

该决定适用于 `DIGITAL_TRANSFORMATION`、`SAFETY_INTELLIGENCE` 和 `INDUSTRY_UPDATE`，三类继续复用同一 Event 详情契约和页面组件。类型差异由 `primary_type`、`facets`、`claim_basis` 和可选热点理由表达，不创建三个详情页。

prototype 已完成并由 Owner 选择 B，但它是 throwaway 设计证据。当前正式 `apps/web/app/pages/events/[id].vue` 仍为单列第一版；本 handoff 描述的是待 Spec 的正式重建，不得宣称已实现。

## 2. 路由、技术和视觉约束

- 正式页面：`/events/{event_id}`。
- 详情数据：`GET /api/v2/events/{event_id}`。
- 折叠附录：`GET /api/v2/events/{event_id}/appendix`，首次展开时延迟加载。
- 媒体：`GET /api/v2/media/{media_id}/preview|download`。
- Owner 复核工作区：`/review` 与 `/api/v2/review/cases...`；详情页只提供入口和必要的上下文，不复制完整复核工作区。
- 正式前端只使用 Nuxt 4、Vue 3、TypeScript strict、Tailwind CSS、Nuxt UI 4 和现有共享组件。
- 颜色、字体、间距、圆角、阴影和布局只来自 `docs/codex-kit/assets/ui/design_tokens.json`。
- 视觉方向继续采用低饱和牛油果主题、高密度时间线和证据化情报卡；不引入 React、第二套组件库、prototype 运行时依赖、fixture 内容、演示分数或伪 AI 总结。

## 3. 规范术语与证据边界

- `SourceExcerpt`／原文摘录：支持 active AcceptedClaims 的一段连续原文，最多 500 个中文字符，并带 claim 与 evidence locator。正式产品不再称“原文简述”。
- `AISummary`／AI 总结：300–500 个中文字符，包含发生了什么、工程影响与意义、限制与待跟踪；事实段逐段引用 AcceptedClaims，判断段单独标识。
- `ClaimBasis`：`MANUFACTURER_CLAIM / RESEARCH_CONCLUSION / PROJECT_FIRST_PARTY_RECORD / INDEPENDENT_VERIFICATION / AUTHORITY_FINDING`。它说明主张基础，不是置信分数。
- “官方一手来源”和“已人工复核”是独立状态。官方来源不代表 Owner 已审核，人工复核也不把非官方材料变成官方材料。
- 用户可见事实、摘要、理由和类型只来源于 accepted claims；AI 不得补全证据不存在的信息。
- 热点只显示触发路径、独立来源数和理由，不显示总分。

## 4. 宽屏 B 布局

标题区横跨双栏，并保持以下首屏顺序：

1. 主类型与必要的低干扰标签；
2. 标题；
3. 来源名称与原文发布时间；
4. 存在撤回、更正或摘要 stale 时的显著提醒。

标题区下方进入双栏：

| 正文主栏 | 上下文侧栏 |
|---|---|
| 原文摘录 | 来源名称 |
| AI 总结、状态、逐段 claim 引用和判断标识 | 官方一手状态 |
| 允许展示的原文图片或授权图片 | 人工复核状态 |
| 附件列表与实际下载/原站动作 | 原文发布时间、首次发现时间 |
|  | PrimaryType、facets、ClaimBasis |
|  | 热点触发路径、来源数和理由（适用时） |
|  | 原文主动作、材料区锚点与数量 |

侧栏只在不遮挡页头、不超出视口可用高度的范围内 sticky。长内容必须自然滚动，不能形成嵌套滚动陷阱；焦点顺序仍按 DOM 语义，不随视觉双栏跳跃。

页面底部在双栏之后以全宽放置 `ReaderAppendix`，默认折叠。目标信息层级承载自动处理结果、accepted claims、证据事实及定位、已审核关系、自动关系、更正历史和 Owner 纠正入口；当前 v2 appendix 尚未完整提供后三类结构化数据，所需组合 seam 见第 10 节。

## 5. 窄屏语义顺序

移动端恢复单列，不使用只能靠 hover、drawer 或横向滚动发现的关键信息。顺序固定为：

1. 类型、标题、来源、原文发布时间；
2. 更正/撤回/STALE 提醒；
3. 来源上下文：官方性、人工复核、首次发现时间、facets、ClaimBasis、热点理由；
4. 原文摘录；
5. AI 总结及状态；
6. 图片、附件、原文与下载动作；
7. 默认折叠的 ReaderAppendix。

移动端实际下载与原文动作只在第 6 项出现一次；上下文区域不再复制按钮。

## 6. FULL、R3 与 R4 信息层级

| 字段/能力 | FULL 普通阅读 | R3 普通阅读 | R4/未决 |
|---|---|---|---|
| 标题、PrimaryType | 显示 | 显示 | 普通接口 404 |
| 来源名称、官方性 | 显示 | 显示 | 普通接口 404 |
| 人工复核状态 | 与官方性分开显示 | 固定待 Owner 审核 | 只在 Owner 隔离边界显示安全状态 |
| 原文发布时间、首次发现时间 | 显示；缺失发布时间如实说明 | 显示 | 普通接口 404 |
| 原文链接 | 显示 | 显示 | 普通接口 404 |
| facets、ClaimBasis、热点理由 | 显示 | 不投影 | 普通接口 404 |
| 原文摘录 | 显示 | 不投影 | 普通接口 404 |
| AI 总结与状态 | 显示 | 不投影 | 普通接口 404 |
| 图片、附件 | 按许可显示 | 不投影 | 普通接口 404 |
| ReaderAppendix | 默认折叠、按需加载 | 不提供 | Owner 隔离面仅安全元数据与隔离原因 |

R3 页面必须明确显示 `official_source`，同时显示“待 Owner 审核”；不得只显示后者。R4、分类未决和 claim 门禁失败不能先把完整对象返回浏览器再由 Vue 隐藏。

## 7. 原文摘录与 AI 总结的呈现

原文摘录使用引用语义和较高的正文可读性，紧邻证据定位入口，但不在主阅读区展开完整证据链。它不能被改写成 AI 风格的概述。

AI 总结的标题必须同时呈现状态。`SUCCEEDED` 时按段展示，并让每个事实段能打开对应 claim 引用；判断段使用明确的“AI 判断”标识。当前 `AiSummaryV2` 只有 summary 级 `claim_ids` 与 `judgment_paragraphs`，不能严谨表达逐段引用；Spec 应定义结构化 paragraph union，例如事实段携带 `claim_ids`、判断段携带明确 kind，不依赖解析 body 中的标记。

七种状态的用户文案必须确定且互异：

| 状态 | 主阅读区文案与行为 |
|---|---|
| `NOT_GENERATED` | “尚未生成 AI 总结。”保留原文摘录，不暗示系统故障 |
| `PROCESSING` | “AI 总结生成中。”可显示非阻塞进度状态，不隐藏正文 |
| `TEMPORARILY_UNAVAILABLE` | “AI 服务暂不可用，系统恢复后将自动补齐。” |
| `SCHEMA_REJECTED` | “AI 返回结果未通过结构校验，未向阅读页展示。”不得显示被拒绝正文 |
| `INSUFFICIENT_EVIDENCE` | “现有 accepted claims 不足以生成有证据支持的总结。” |
| `SUCCEEDED` | 展示结构化总结、模型标识和必要生成时间；事实段可追溯 claim |
| `STALE` | “原文或已接受事实已变化，现有 AI 总结已失效并等待重生成。”与更正提醒关联，不显示为当前有效总结 |

AI 状态色不能把“未生成”“处理中”“证据不足”“Schema 拒绝”和“临时不可用”压成同一个含混 pending 状态。

## 8. 动作、图片和附件

### 8.1 动作去重

- 只渲染一份响应式 `ReaderActions`：宽屏把它放在侧栏，包含“查看原文”主动作以及跳转到材料区的锚点和数量；窄屏把同一组动作移到 AI 之后的材料区。
- 正文材料区只放实际图片、附件原站链接和下载动作；移动端不复制任何下载按钮。
- Owner 纠正使用一个清楚的 `/review` 入口，并携带当前 Event/Case 上下文；详情页不复制确认/排除、claim 替换或重生成表单。

### 8.2 图片

- 只有公共领域、明确许可、来源授权或 Owner 自有素材可以展示。
- `preview_url` 为 `null` 时不得渲染空 `img`；显示名称与不可预览说明即可。
- 可预览图片只通过同源 `/api/v2/media/{media_id}/preview` 安全派生资源，不使用远程图片 URL 直连。
- 图片有真实、简洁的替代文本；装饰性素材不进入内容媒体列表。

### 8.3 附件

- 扫描通过且允许再分发时，下载走同源 `/api/v2/media/{media_id}/download`，服务端再 302 到最长 300 秒的私有签名地址。
- `redistribution_allowed=false` 时只显示附件名称与 `source_url` 原站链接，不渲染下载按钮。
- 下载失败、签名过期或扫描状态变化要以就地错误反馈处理，不让用户误以为原文证据不存在。

## 9. ReaderAppendix 的折叠要求

- 默认折叠，按钮具有正确 `aria-expanded` 和可见焦点；展开后把焦点保持在触发器或移动到清楚的附录标题，不能跳到页面顶部。
- 首次展开才请求 appendix；加载、空、错误、重试和成功状态分别呈现。
- 大量 claims/evidence/关系时采用分组、渐进展示或现有虚拟化能力，不能一次把重型诊断内容挤入主阅读流。
- 自动结果与 accepted claims 必须明显区分；未接受的 AI 候选不能伪装成证据事实。
- 目标更正历史按时间顺序呈现，STALE 摘要与触发它的原文/claim 变化可关联查看；在结构化契约补齐前不得从 `list[str]` 猜测时间或关联。
- Owner 纠正入口复用 `/review`，不在附录复制完整 review workspace；只有服务端提供 Event 到 ReviewCase 的安全只读上下文后才生成深链接，否则进入 `/review` 列表。

## 10. 当前契约与正式页面差距

下一份 Spec 不能把以下项目写成已经完成：

1. `EventFullProjectionV2` 有 `source.official`，但缺少普通阅读面独立的人工复核状态。
2. `EventMetadataProjectionV2` 已有 `official_source`，正式 R3 页面却未展示。
3. `AiSummaryV2` 只有 summary 级 claim 引用，尚不能满足逐段 claim 引用；`body` 当前只要求至少 30 个字符，也未落实已确认的 300–500 字用户可见总结约束。
4. 正式页面尚未呈现 facets、ClaimBasis、热点触发路径/独立来源数/理由、官方与人工复核双状态或 AI 判断段标识。
5. 正式 CSS 仍是单列 grid，B 双栏和受约束 sticky 未实现。
6. 图片当前会在 `preview_url=null` 时渲染空 `src`；附件动作尚未按再分发许可解释清楚。
7. appendix 当前只显示计数，缺少独立错误/重试/空/重内容和焦点稳定处理。
8. `EventAppendixV2` 只有 `automatic_results`、已审核 `relationships` 和无时间结构的 `corrections: list[str]`，没有 `automatic_relationships`，Event 阅读投影也没有 `case_id`。现有自动关系读取与纠正仍通过 `GET /api/v1/events/{event_id}/automatic-relationships` 和 `POST /api/v1/events/{event_id}/relationship-corrections`。Spec 必须冻结一种组合方式：继续由 appendix 组合这些保留的 v1 能力并补足更正/复核只读上下文，或显式扩展 v2 appendix；不得假设当前 v2 契约已提供这些数据。

这些差距应以契约测试先行的纵向切片实现，不能在 Vue 中通过猜测字段或硬编码文案绕过服务端契约。

## 11. 最少但最高层级的验收矩阵

### 契约与 API

- FULL、R3 和 R4/404 字段白名单；官方性与人工复核状态独立。
- AI 逐段 fact/judgment 判别联合与七状态互斥 payload。
- 无可见热点总分；R3 不泄漏正文、claims、AI、媒体；R4 普通接口不泄漏安全元数据。
- media preview/download 同源路径和 `redistribution_allowed=false` 行为。

### Nuxt E2E 与可访问性

- B 桌面双栏、sticky 边界、超长侧栏和主栏滚动；至少覆盖大桌面、普通桌面、平板断点附近和窄屏。
- 移动端固定语义顺序、无重复下载动作、键盘与屏幕阅读器顺序一致。
- 三个 PrimaryType 使用同一页面；facets、ClaimBasis 和可选热点理由按数据增量展示。
- 七个 AI 状态、更正提醒与 STALE 关联、事实段 claim 引用和判断标识。
- 图片可预览/不可预览、附件可下载/仅原站链接、签名或请求失败。
- appendix 的未加载、加载、空、成功、错误、重试、大数据和焦点稳定。
- R3 显示 official source + pending review；R4 和无投影显示统一不可见结果。
- axe、键盘操作、200% 缩放、长标题、长来源名、缺失发布时间和减少动画偏好。

## 12. 明确不做

- 不创建数字化、安全和行业更新三套详情页。
- 不把证据事实、自动结果、关系或 Owner 工作区提升到正文主栏。
- 不把 hotspot 分数、演示分数或“可信度”聚合分数放到普通页面。
- 不镜像受版权保护的全文、无许可图片或附件。
- 不把 prototype 的 React/静态组件、fixture、截图或自定义 token 复制到生产。
- 不绕过或改变 PublicationService 的发布决策、R3/R4 ACL、来源准入或多用户认证边界；允许在这些边界内扩展并生成本轮新增的只读投影字段。

## 13. 规格入口

本页面没有剩余产品决策，可以直接进入 `to-spec`。规格需把契约增量、迁移兼容、组件拆分、响应式语义顺序、状态文案和上述 E2E 矩阵写成可验收纵向切片。

输入资料：

- [总体共同理解 handoff](srbg-intelligence-v2-shared-understanding-to-spec-handoff-2026-07-19.md)
- [Publication & Reader Projection Context](contexts/publication-reader/CONTEXT.md)
- [Evidence & AI Context](contexts/evidence-ai/CONTEXT.md)
- [v2 验收记录](acceptance/phase-2/intelligence-quality-reader-v2.md)
- [prototype 输入记录](codex-kit/prototype/owner-reader-detail/HANDOFF.md)
- prototype 结果：`D:\CodexProjects\srbg-intelligence-platform-owner-reader-prototype\docs\codex-kit\prototype\owner-reader-detail\RESULT.md`
- prototype 观察：`D:\CodexProjects\srbg-intelligence-platform-owner-reader-prototype\docs\codex-kit\prototype\owner-reader-detail\OBSERVATIONS.md`
