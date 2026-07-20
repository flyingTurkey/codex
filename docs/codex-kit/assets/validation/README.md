# 验证素材使用说明

本目录提供“策略即代码”的设计契约，供 Codex 在实现过程中转成服务端规则、契约测试和 CI 门禁。

## 文件职责

- `publication_gate.json`：唯一发布策略。默认拒绝，且只接受服务端从数据库和安全审查记录生成的权威上下文。
- `publication_evaluation.schema.json`：发布策略的输入契约。前端、采集器或模型不得直接提交或覆盖 `server.*` 字段。
- `quality_gates.json`：质量指标及最低阈值。
- `source_onboarding_checklist.json`：来源从候选到启用的检查清单。
- `readiness_evidence.schema.json`：临近生产发布时由 CI 生成的就绪证据清单。
- `t14_source_stream_research.schema.json`：有界 SourceStream 发现记录的研究关闭契约；`ADMISSION_READY` 不授予实际准入或运行权。
- `t14_mohurd_source_stream_research.json`：Issue #15 的住建部点时研究证据；只表达研究处置，不授予准入或运行权。
- `t27_source_stream_discovery.schema.json`：Issue #28 两个机构 Source 的 v2 研究契约，固定万方替代期刊集合、两流关闭资格、无运行证据和逐机构处置语义。
- `t27_chts_tunnel_construction_source_stream_discovery.json`：中国公路学会工程成果集合与万方 ISSN `2096-4498` 期刊替代流的点时证据；官方站阻断被保留，但替代流使本票满足研究关闭条件，仍不授予准入或运行权。
- `t29r_jace_cccc_source_stream_discovery.schema.json`：Issue #39 替代流的失败关闭契约，固定 JACE 当前刊期 API/query、研究结论 ClaimBasis 与两流无运行权限。
- `t29r_jace_cccc_source_stream_discovery.json`：《建筑科学与工程学报》与中国交建的点时研究记录；未固化的浏览器响应哈希保持 `null`，`ADMISSION_READY` 不代表已准入或运行。

## 哈希的边界

哈希是证据完整性和生产发布审计能力，不是初版开发启动条件：

- 设计文档、CSV、YAML、JSON、SVG 和静态示例不需要先计算哈希即可打开、预览或用于前后端联调；
- 本地 fixture 导入可由服务端自动计算 SHA-256，不要求开发者手工维护；
- 只有进入真实采集、发布修订或生产就绪判定时，相关服务才必须计算并核验哈希；
- 缺少生产哈希时应阻止正式发布，但不得阻止仓库初始化、页面开发、测试数据预览和非发布型演示。

## 不可信边界

`content.schema.json` 是已发布内容的只读模型，不能作为模型候选或发布审核的写入接口。模型输出依次使用 `assets/schemas/` 中的步骤契约，最终由 `PublicationService` 重新查询服务端权威上下文并执行 `publication_gate.json`。

任何 API、后台按钮、批处理或管理员脚本都不得绕过该服务直接写入发布修订表。
