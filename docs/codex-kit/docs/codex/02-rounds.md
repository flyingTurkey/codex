# 第 00A—11 轮实施总表

本文件用于快速查看每轮范围。执行时优先复制各轮独立指令文件。

| 文件 | 读取的主要素材 | 关键门禁 |
|---|---|---|
| `round-00a-ui-foundation.md` | 方案1视觉稿、UI Token、组件与状态规范 | 不重脚手架；应用壳层、断点、键盘和axe通过 |
| `round-01-source-vault.md` | 来源CSV、来源合规规范 | 重复上传不产生重复原始对象 |
| `round-02-safety-regulation-html.md` | 内容Schema、分类本体、发布门禁v2 | 官方HTML进入待审核，且只能通过唯一PublicationService发布 |
| `round-03-pdf-ocr-versioning.md` | 证据模型、安全规范 | PDF替换触发差异和摘要失效 |
| `round-04-safety-case-lifecycle.md` | 事故标签、状态关系 | 初报和调查报告不被去重删除 |
| `round-05-digital-cases.md` | 数字化示例、UI文案 | 厂商声明不显示为平台确认 |
| `round-06-papers.md` | OpenAlex、题录示例 | DOI优先去重且不复制未授权全文 |
| `round-07-products-equipment.md` | 产品/低空标签 | 产品能力不推导许可或适用资格 |
| `round-08-dedup-events-scoring.md` | 关系和评分 | 转载不重复计独立信源 |
| `round-09-ai-editorial.md` | Prompt、Schema、既有门禁 | 扩展PublicationService并消除所有绕过发布路径 |
| `round-10-feed-search-daily.md` | 页面清单、设计令牌、既有Feed/Card | 组合完善selected/all/search/daily，不重建平行组件 |
| `round-11-production-gates.md` | SLO、安全、运维、就绪证据Schema | CI强制门禁、恢复演练和独立验收证据包 |

第 00A 轮不改业务数据库与 API；第 01—11 轮均须完成适用的迁移、后端、API、前端、测试、观测、文档和 Git 提交，不接受只完成其中某一技术层。

第 02 轮冻结 `FeedPage`、`ItemSummary` 和 `IntelligenceCard` 的第一版契约；第 02—07 轮持续扩展同一信息流；第 08 轮开放真实分项评分；第 10 轮只做组合、完善和状态收口。
