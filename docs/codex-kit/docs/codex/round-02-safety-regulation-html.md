# 第 02 轮：首个安全规定 HTML 来源

```text
执行第02轮：以一个经过准入的官方HTML安全规定来源，打通自动发现到人工审核发布。

读取：docs/codex-kit/docs/01-PRD.md、docs/codex-kit/docs/02-content-model.md、docs/codex-kit/docs/04-data-source-compliance.md、docs/codex-kit/docs/06-ui-ux-spec.md、docs/codex-kit/docs/ui/02-component-contracts.md、docs/codex-kit/docs/ui/03-page-state-matrix.md、docs/codex-kit/assets/taxonomy.yaml、docs/codex-kit/assets/content.schema.json、docs/codex-kit/assets/validation/publication_gate.json、docs/codex-kit/assets/validation/publication_evaluation.schema.json。

目标：定时发现公开列表的新文件，下载原文，解析标题/发布机关/文号/发布日期，生成字段证据，进入审核队列，经审核后在安全频道和详情页展示。

来源选择：优先使用交通运输部政府信息公开或应急管理部。若在线访问在开发环境不稳定，必须以已审核的固定样本完成确定性测试，真实抓取作为可配置适配器。

必须交付：
- SourceConnector和DocumentParser协议；
- source_checkpoint、fetch_run、fetch_record、processing_run、intelligence_item、safety_regulation_profile、claim、claim_evidence、review_task、publication及revision迁移；
- 从本轮开始实现唯一的服务端发布入口 `PublicationService`，所有审批、发布、修订、撤回和重发必须调用它；
- `PublicationService` 必须使用 `publication_gate.json` v2 和服务端可信上下文执行默认拒绝门禁，候选内容自报的来源等级、评分、审核状态或证据结果不具有授权性；
- 数据库仅向专用的发布服务角色授予 `publication` 和 `publication_revision` 写权限，API、Worker、管理员和模型角色都不得直写；
- 发现、游标、条件请求、重试、限速、熔断、幂等和SSRF防护；
- HTML段落编号和证据定位；
- 基于受控枚举的安全规定分类；
- 文号、机关、发布日期使用规则解析并与证据绑定；
- R3强制人工审核和职责分离；
- R3 安全内容在审核通过前，普通用户的查询投影只能返回标题、来源、时间、原文链接和“待审核”状态；不得返回 AI 摘要、效力结论、归责、伤亡、原因或其他高风险字段；
- 安全列表、详情、证据抽屉、审核工作台最小版；
- 采集运行和审核审计；
- 连接器契约、解析黄金、集成、RBAC、E2E测试。

方案1 UI与契约基线：
- 从本轮开始冻结 packages/contracts 中 FeedPage、ItemSummary、FeedNotice 和 TypeSummary v1；
- GET /api/v1/feed?mode=selected|all 返回扁平Cursor列表，由前端按Asia/Shanghai对activity_at分组；
- 复用第00A轮壳层，新建且只新建一套 TimelineFeed、IntelligenceCard、EvidenceDrawer、FilterPanel；
- 完成 /selected、/all、/safety 和最小 /items/:id；
- 第08轮前真实评分不存在时隐藏评分区域，不生成演示分数；
- R3受限投影必须在服务端完成，前端不能收到被限制字段。

发布门禁：`PublicationService` 必须使用服务端现查的来源策略、文档当前版本、证据覆盖、审批人和职责分离结果执行 v2 门禁。无主来源、无原文URL、文号/日期无证据、法规效力由候选数据推断时禁止发布或精选。法规状态默认UNKNOWN，除非服务端核验的官方证据和有权审核决定共同支持。

验收场景：固定来源出现一条新规定→自动抓取→待审核→普通用户只看到 R3 白名单字段→审核员查看证据并批准→`PublicationService` 通过 v2 门禁后安全频道显示；再次运行不重复；viewer无法审批；提交人无法审批自己的R3内容；绕过服务直写发布表被数据库权限拒绝。

验收：固定样本能在同一时间线中从R3受限卡变为已人工复核完整卡；make fixture-replay quality-gate web-e2e web-a11y 与全局门禁全部通过。

不做：PDF/OCR、复杂修订关系、事故、AI摘要。
```
