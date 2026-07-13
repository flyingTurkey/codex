# UI 05｜前后端纵向切片映射

## 核心原则

方案 1 是从第一条内容开始持续生长的主产品界面，不是第 10 轮再套的一张皮。

- 第 00A 轮建立设计系统与应用壳层；
- 第 02 轮冻结第一版 Feed 与 ItemSummary 契约；
- 第 02—07 轮持续扩展同一个 `IntelligenceCard`；
- 第 08 轮才开放真实分项评分；
- 第 10 轮只组合、完善和收口，不重写 Feed/Card。

| 轮次 | 用户可见增量 | 复用/新增组件 | 后端/API 增量 |
|---:|---|---|---|
| 00A | 牛油果主题与壳层 | AppShell、Sidebar、PageHeader、基础状态 | 无业务表和 API 变更 |
| 01 | 来源登记、样本上传、预览 | AdminTable、SourceForm、DocumentPreview | 来源、策略、原始对象、版本 |
| 02 | 首条安全规定进入全量/精选 | TimelineFeed、IntelligenceCard、EvidenceDrawer | 冻结 FeedPage、ItemSummary、PublicationService 投影 |
| 03 | PDF 证据、版本与撤回 | PdfEvidence、VersionTimeline、DiffView | 页码证据、版本差异、摘要失效 |
| 04 | 安全案例生命周期 | EventTimeline、Confirmed/Unverified 分区 | Event、关系、冲突、R3 门禁 |
| 05 | 数字化案例 | Digital TypeSummary、成熟度与场景筛选 | DigitalCase、实体、相关性 v1 |
| 06 | 论文 | Paper TypeSummary、引用复制 | Paper、DOI、开放状态 |
| 07 | 软件/物联网/低空/AI设备 | Product TypeSummary、声明/验证分区 | Product、Vendor、Model、APPLIED_IN |
| 08 | 热点与可解释评分 | ScoreBreakdown、Topic、SourceCompare | 聚类、独立信源、分项评分 |
| 09 | 完整审核闭环 | 三栏 ReviewWorkbench、门禁状态 | AI 流水线、发布修订、撤回 |
| 10 | 搜索、日报、收藏、全部状态 | 组合并完善既有组件 | search/daily/saved/fingerprint/version |
| 11 | 运维与质量看板 | Quality、Run、SourceHealth | SLO、告警、恢复、就绪证据 |

每轮的可复制指令仍以 `docs/codex/round-*.md` 为准。先执行 `round-00a-ui-foundation.md`，再继续第 01 轮。

