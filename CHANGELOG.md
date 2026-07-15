# Changelog

所有重要变更记录在此文件。

## [Unreleased]

### Round 14 — Event 统一身份、关系拆分与 Item 兼容迁移

- 完成独立验收指出的收口项：`published_v1` 升级为 1.1.0 Event 修订投影，默认普通 Feed/Event/搜索/已发布日报/收藏读取装配到 `srbg_projection_reader_login`；搜索投影、日报快照、收藏、专题和反馈的新事实均携带或仅写入 `event_id`，Event 详情页由单一接口返回 claims、evidence、documents、来源对比与类型详情。新增 `0014b_event_consumer_switch` 的 `SHADOW/EVENT/ROLLBACK_READ_ONLY` 权威开关和只读回滚保护，并以非空 TEST PostgreSQL 数据对旧收藏、专题、日报、反馈、搜索、publication revision、event revision 与 R3 ACL 完成 1:1 对账。
- 独立验收修复了应用回退到 0013 时读取 0014 Event 列及 alias 权限导致的失败，并补齐五类身份迁移告警和 Runbook。复验同时确认本轮仍未完成：默认普通读取装配和多个 consumer 查询仍走业务表/`item_id`，与专用 `published_v1` 和单次 Event consumer switch 约束不符；README 与验收结论已改为 `NOT_COMPLETED`，没有以现有绿测掩盖该架构差异。
- 扩展现有 Event 为显式通用事件模型，增加稳定 canonical identity、版本、合并/拆分/回滚工作流和不可变 Item alias；没有创建平行事件服务或 `PROVISIONAL_EVENT`。
- 分离 Document 来源角色、Event 生命周期、Event-Entity、Topic-Event 和受控分类关系；八类 Item 显式映射 Event 类型，模糊匹配只生成候选且 `auto_merge` 保持关闭。
- 以版本化、幂等、可断点恢复任务完成 shadow backfill 和 consumer parity；已发布 Item 身份 23/23 可解析，差异为 0，23 条未知来源角色进入人工队列。
- Feed、搜索、日报、收藏、专题、下载和详情在一次 consumer switch 中改用 Event；旧 Item 页面只返回 308，读取 API 返回 `Deprecation/Link` 和可配置 `Sunset`，旧写接口返回 410。
- 合并、拆分和回滚经 reviewer、`PublicationService` 与追加式审计执行；新增 Round14 专项门禁、真实 PostgreSQL 引用完整性测试、兼容 E2E、R3/R4 越权测试和迁移/别名/候选/回滚指标。

### Round 13 — 内部发布投影、Event 身份与权限隔离

- 新增 Alembic `0013_internal_projection` 和版本化 `published_v1` schema，以稳定 Event 公开 ID 保存 `PublishedEventSummaryV1`/`PublishedEventDetailV1` 影子投影、字段来源、generation、publication revision、生成时间、失效原因和审计引用；既有 `publication_projection_state` 继续只负责搜索、缓存与日报失效。
- 拆分并约束 `publication_risk_tier`、`content_severity`、`projection_level`，保留旧 `risk_level` 的精确兼容映射和可回滚路径；R3 待审核仅生成官方题录 `METADATA_ONLY`，服务端排除精选、日报、推荐、通知和全文导出，R4 始终零投影。
- 新增 PublicationService writer 边界内的幂等影子回填与对账：本地验收数据形成 32 个稳定 Event、23 条 `FULL`、9 条 `METADATA_ONLY`，连续两代 source/projected 均为 32、差异为 0；未切换现有 Feed、搜索、日报、收藏、专题或详情消费者。
- 新增真实 PostgreSQL 低权限 `srbg_projection_reader` 登录验证，只能读取版本化发布视图，不能获得业务 schema/table、原始对象、审核备注、审计表、R4 数据或投影基表的 `USAGE/SELECT`；查询、游标、旧 generation、搜索和导出绕过均有负向测试。
- 收紧 OIDC/RBAC：非开发环境拒绝本地身份头，验证 issuer/audience/RS256/kid/exp/nbf/iat/角色和 JWKS 默认拒绝；来源启停与发布职责分离，高权限写操作要求短时 MFA step-up，CORS 使用精确 allowlist，Nuxt 代理不转发客户端伪造身份头。
- 撤销运行角色对 `audit_log` 的直接写权限，通过受控数据库函数计算链值，并把链根锚定至独立对象存储；该能力仅称 append-only/tamper-evident，不宣称对数据库管理员绝对不可篡改。
- 新增投影生成/失效、权限拒绝、R3 降级和对账差异的结构化日志及低基数指标，新增 `make phase2-round13-test`、迁移正反向回放、发布路径审计、Web E2E/a11y 无破坏回归，并更新 README 与本轮验收记录。
- 独立复验修复回填 CLI 绕过 `PublicationService`、accepted claim 字符串二次 JSON 编码、运行时投影/锚定健康指标缺失和审计锚定未定期调度的问题；新增 PostgreSQL 权威指标、每日锚定、Prometheus 差异/陈旧告警、fail-closed Runbook，以及真实 reader/runtime 权限与结构化拒绝日志负向测试。

### Round 12 — 真实能力审计与二阶段基线

- 新增 `docs/audit/phase-2/` 十二项只读审计产物，以代码、实际数据库登录、运行API、测试和外部证据重新分类来源、连接器、Event/Item、发布投影、R3/R4、审计日志、用户行为、模型、指标和150来源风险；没有把CHANGELOG或方案声明当作实现证据。
- 确认46条种子均为CANDIDATE，运行库54条ACTIVE全是固定/集成测试来源，108次采集全为FIXTURE；因此真实端到端追踪为`NOT_AVAILABLE`，生产模型、通知、国际来源、连续运行和真人金标指标均保持null。
- 实测API/Worker登录可读写大量业务表和audit_log，普通用户尚无专用只读发布投影；audit_log可由运行角色自造INSERT、仅UPDATE/DELETE受不可变触发器阻止，且无独立hash根锚定。Event/Topic运行数据为空，门户、发布、搜索、日报和收藏仍以Item为身份。
- 全局quality gate、Round08—11、42项E2E和13项a11y通过；Round02—04旧专项因隔离迁移边界缺少`ai_pipeline_run`失败，smoke因旧版本响应断言失败，严格真人金标/readiness按设计BLOCKED。本轮未修改业务代码或测试阈值，结论保持未完成。
- 独立验收以失败测试复现并修复上述工程漂移：隔离集成默认回放当前0012 head，smoke校验完整版本契约并按权威Feed区分空态/有数据状态；同时修复未评分已发布内容进入`/selected`的回归。Round01—11专项、quality gate、fixture replay、smoke、42项E2E和13项a11y现均通过；严格真人金标/readiness仍因五类真实样本为0保持BLOCKED。

### 二阶段文档基线

- 固化企业内部 OIDC/SSO、Event 唯一用户身份、R3 `METADATA_ONLY`、Item 只读兼容、确定性归并和专用只读发布投影等已确认决策，删除匿名公开、`PROVISIONAL_EVENT`、R0、1000 候选硬指标和 `source_trust_score` 等冲突要求。
- 将执行顺序统一为 11F、11P、12—21，并按 20→50→100→150 来源门禁安排 AI、外部通知和国际来源；明确第 11 轮工程切片 `PASSED` 与生产证据 `BLOCKED` 是不同状态，第 12 轮无获准 ACTIVE 来源时真实追踪记录 `NOT_AVAILABLE`。
- 更新 README 的现状与文档导航；本次仅固化文档，不修改业务代码、数据库、依赖、配置、测试阈值或运行环境。

### Round 11 — 质量、运维、安全与上线门禁

- 新增 PostgreSQL 权威的最小失败任务、优先级人工重放、不可回溯个人的聚合运行指标和显式反馈；失败记录不保存正文、令牌、Cookie、模型输入、个人敏感 Payload 或关联哈希，解析/AI 重放在无法安全重建时默认失败。复用唯一 `PublicationService` 及既有 Feed/卡片/AppShell，交付来源健康、运行中心和质量看板。
- 接入固定版本 Prometheus/Grafana/Alertmanager/OpenTelemetry 与 Sentry 配置，增加来源、队列、解析、AI、审核、API、搜索、成本、SLO/错误预算和备份验证告警基线。
- 新增隔离恢复演练、负载/成本基线、环境隔离、发布/回滚/撤回/来源故障/模型异常/Redis 重建 Runbook，以及 OIDC RS256/JWKS、依赖/密钥/配置和发布对抗门禁。
- 新增版本化金标目录、readiness Schema/评测器和 CI required checks；工程 CI 成功校验 Schema、引用完整性及诚实 `BLOCKED`，严格 golden/readiness 保持非零晋级门禁。证据主体区分 AGENT/CI/HUMAN，证据包记录空金标、短实测窗口和未配置生产路由，生产状态保持 `BLOCKED`。

### Round 10 — 信息流、搜索、专题与日报

- 在既有 `/api/v1/feed?mode=selected|all`、`/items/{id}`、`/events/{id}` 和 `/hot-topics` 上统一补齐签名 Cursor 分页、组合筛选、ACL 投影和稳定 ETag/304；新增 `/search`、`/daily`、`/reports/{id}`、`/fingerprint`、`/saved-items` 与私有专题接口，没有创建平行 `/items` 或 `/events` 列表。
- 新增 Alembic `0011_feed_search_daily` 与 PostgreSQL 17.10 + pg_trgm/pgvector 基础：编号、文号、标准号和 DOI 规范化精确匹配永远排在标题/实体/标签 trigram、中文正文 bigram FTS 与可选语义召回之前；语义能力默认关闭、超时可降级，不能压过精确编号结果。
- 收藏和自定义专题按用户隔离并在读取时重新应用当前 ACL；写入支持 Idempotency-Key，专题修改使用 If-Match。R3 仍只返回服务端白名单投影，R4 和管理内容不进入普通用户响应。
- 日报草稿以固定 publication revision 快照生成，只能由 reviewer 审核后经唯一 `PublicationService` 发布；已发布日报保持历史标题和顺序，当前撤回状态以文字覆盖且不泄露旧摘要。新增 Markdown 导出，并对可能触发表格公式的前导字符执行转义。
- 扩展既有发布投影 Worker，使发布、修订和撤回同步维护搜索与日报 generation/visible 状态；详情继续复用 accepted claim、事实清单、证据抽屉、来源冲突与版本时间线，原文失效、来源延迟、撤回和无 AI 均有显式降级状态。
- 复用 `AppShell`、`IntelligenceFeedPage`、`TimelineFeed`、`IntelligenceCard` 和冻结的 `FeedPage`/`ItemSummary`，新增搜索、日报、收藏页面并完善首页、精选、全部、数字化和安全频道；首页首屏展示今日重点、数据更新时间和异常提示，不使用装饰 Hero。
- 搜索与收藏页面通过共享 Feed 的加载更多契约追加 Cursor 页；首页视觉基线覆盖 1920×1080、1440×900、1024×768、768×1024，安全/撤回状态均同时使用文字，768 阅读宽度和 200% 等效视口保持可操作。
- 新增迁移回放、搜索排序/游标/ETag/ACL、日报快照/发布、收藏专题、投影 Worker、性能 SLO、Playwright 关键路径和 axe 测试；部署实测搜索 40 次 P95 31.05 ms，低于 800 ms 门槛。

### Round 09 — 受控模型网关、审核治理与发布版本

- 新增无工具能力的受控模型网关、确定性 Mock provider 和可配置 OpenAI 兼容 provider；分类、事实抽取、摘要、发布前复核四步均绑定不可变 Prompt、JSON Schema、模型参数、输入 SHA-256、原始/校验后输出、Token、微美元成本和耗时。
- 新增 Alembic `0010_ai_editorial_governance`，保存 AI 运行、Prompt/Schema/模型版本、注入扫描、安全决定、内容审核决定、历史回放、影子结果、质量报告及发布投影状态；AI Worker 使用独立队列且没有数据库、对象存储、Shell 或工具权限。
- 将唯一 `publication_gate.json` 升级为 `2.1.0`，由唯一 `PublicationService` 现查来源、当前文档、证据、审核、风险和安全事实；模型自报的来源等级、审核状态、风险、安全处置和发布建议均不能授权发布，R3/R4、事故原因/责任和法规效力保持强制人审。
- 扩展原有发布服务完成批准、拒绝、纠错、修订、撤回和重发的不可变 `review_decision`/`publication_revision` 工作流；API、后台动作、Worker 和脚本的发布路径审计确认不存在平行入口，应用层与 PostgreSQL 最小权限共同阻止直写发布表。
- 发布、修订和撤回在同一事务推进搜索、缓存和日报投影 generation；publisher worker 经 `PublicationService` 消费投影事件并原子更新 Redis generation/visible 指针，撤回后旧缓存版本不可达，已发布修订快照不被模型升级静默改写。
- 复用 `AppShell`、`IntelligenceFeedPage`、`TimelineFeed`、`IntelligenceCard`、冻结的 `FeedPage`/`ItemSummary`、`PdfEvidenceViewer`、`FactList`、`EvidenceDrawer` 和 `StatusBadge`，新增三栏 `ReviewWorkbench`，并在信息流/详情增量展示 AI 辅助、Prompt/Schema/模型版本、无 AI 降级、修订和撤回状态；完整摘要只允许引用 accepted claims。
- 新增恶意固定样本、模型输出对抗、发布绕过审计、迁移/RBAC、fixture replay 和质量报告；覆盖忽略指令/密钥泄露、额外字段、错误 JSON、伪造 evidence_id、无证据事实、企业声明缺归因以及伪造审核/权威/安全处置。

### Round 08 — 去重、事件聚类、热点和评分

- 新增 Alembic `0009_dedup_events_scoring`，统一保存 URL/外部 ID/DOI/机构域内文号/哈希身份键、正文指纹、重复候选与决定、来源谱系、主题聚类、八维评分、人工覆盖和回归样本；决定与审计均为追加式，运行角色不能直接写人工决定。
- 实现规则候选召回和可选 pgvector 召回的并集，最终合并始终先执行项目、标段、型号、文号和事故阶段硬约束；修订、澄清、撤回、更正及后续材料形成关系，不按重复删除，生产自动合并固定关闭。
- 识别转载链和同机构镜像并按独立来源主体计数；将事件扩展到安全事故、法规变化、数字化项目、研究成果和产品发布，新增事件/主题/关系人工工作台，所有决定必须填写理由并经唯一 `PublicationService` 写审计和回归样本。
- 新增相关性、权威、影响、新颖、时效、证据、置信和热度八个独立分项，保存特征解释、规则版本、原始分和人工覆盖理由；热度不参与置信分计算，普通卡片最多显示一个明确命名的“相关度”入口。
- 复用 `AppShell`、`IntelligenceFeedPage`、`TimelineFeed`、`IntelligenceCard`、`FeedPage`/`ItemSummary`，新增 `/hot`、事件来源对比和 `/admin/clusters`；同一通稿转载不会增加热点独立信源数。
- 新增 300 对重复/非重复与 100 事件的首版内部固定金标结构、离线精确率/召回率/聚类纯度评测、迁移/RBAC/契约/API/E2E/axe 测试和 `make round08-test`/`make round08-eval`。样本尚未人工裁定，结果明确标记为内测评估，不能据此开放自动合并。

### Round 07 — 软件、物联网、低空和 AI 设备

- 新增 Alembic `0008_technology_products`，以统一 vendor/product/model/version/profile/capability/taxonomy 模型表达四类技术产品；型号和版本分别保持唯一身份与历史记录，同名不同型号不静默合并，疑似别名、后继版本和重复项进入人工归一候选。
- 将厂商声明与独立验证能力在数据库约束、契约、publication gate `7.0.0`、统一 API、共享卡片和详情页全链路分离；已验证能力必须携带独立证据，任何产品内容不得生成“四川路桥采购”结论。
- 复用既有来源准入和统一 `SourceAdapter`，提供广联达软件与大疆低空设备的最小固定回放；ENT-007/008 继续保持 `CANDIDATE/disabled`，固定样本不授予生产采集资格，厂商图片默认不下载。
- 增量扩展冻结的 `FeedPage`、`ItemSummary`、`TypeSummary` 与详情契约，在同一 `/api/v1/feed`、`/api/v1/items/{id}`、`/digital` 和 `IntelligenceCard` 支持 SOFTWARE_PRODUCT、IOT_PRODUCT、LOW_ALTITUDE_EQUIPMENT、AI_EQUIPMENT 及产品类型、证据等级、部署方式、场景和成熟度筛选。
- 产品详情统一显示“产品能力/工程证据/许可与限制”，通过经审核的 `APPLIED_IN` 关系连接数字化案例；低空设备固定提示“产品发布不代表空域、适航、飞手和项目许可。”，无官方许可证据时许可状态为 `UNKNOWN`。
- 在既有审核工作台增加 reviewer 专用型号/版本归一入口，所有决定只经唯一 `PublicationService` 写入并追加审计；新增按类型/证据/许可、能力分组及待归一队列指标，以及契约、迁移回放、门禁、固定回放、E2E 和 axe 测试与 `make product-test`。

### Round 06 — 期刊论文

- 新增 Alembic `0007_papers`，以论文题录、作者/机构、来源记录、受控分类、候选去重和经审核的更正/撤稿关系表达学术元数据；DOI 使用规范化唯一索引，无 DOI 时以规范题名、首位作者和年份生成候选指纹，并完成 `0006 → 0007 → 0006 → 0007` 隔离回放。
- 接入统一 `SourceAdapter` 下的 OpenAlex 游标分页连接器与 Crossref DOI/更新关系补充器；共享 HTTP 客户端统一执行域名白名单、超时、限速、礼貌 User-Agent、条件请求、有限重试、熔断和 `Retry-After`，固定响应不授予生产来源 active 权限。
- publication gate 升级至 `6.0.0`，由唯一 `PublicationService` 校验论文身份、accepted claim、研究成熟度、访问许可和更正/撤稿关系；运行角色不能直接写正式关系，未授权全文永不落入对象存储或浏览器响应，摘要许可不清时仅投影题录和原文链接。
- 增量扩展冻结的 `FeedPage`、`ItemSummary`、`TypeSummary` 与详情契约，提供 DOI、期刊、ISSN、作者、机构、卷期、年份、关键词、开放状态、论文类型、工程专业、技术标签、研究成熟度、相似论文、RIS/BibTeX/GB/T 7714 引用及原文入口。
- 复用 `AppShell`、`IntelligenceFeedPage`、`TimelineFeed` 和 `IntelligenceCard`，在既有 `/digital` 增加论文 Tab、筛选、共享卡片和详情；元数据、摘要、全文权限分区显示，撤稿/更正显著提示，并明确“研究结果不代表已完成工程生产应用”。
- 新增 OpenAlex/Crossref/中国公路学报固定样本、API Mock、版权边界、迁移/契约/门禁/固定回放/E2E/axe 测试和 `make paper-test` 专项门禁；知网、万方维持授权 API 或人工题录方式，禁止绕过登录或付费机制。

### Round 05 — 数字化转型案例

- 新增 Alembic `0006_digital_cases`，以数字案例档案、受控分类、企业/技术/项目实体关系、claimed/verified 成效和 `relevance-v1.0.0` 分项事实表达数字化案例；空库支持 0005→0006→0005→0006 回放，存在数字案例数据时拒绝破坏性降级。
- 接入交通运输部政府案例汇编与蜀道集团企业案例两个统一 `SourceAdapter`，Git 仅固定短摘录、原文 URL、PDF 页码和 SHA-256；生产来源保持 `CANDIDATE/disabled`，不能由样本自报 active。
- publication gate 升级到 `5.0.0`；分类、成熟度、归因、独立证据、允许动作和相关性规则均由服务端权威上下文默认拒绝校验，企业自述未经职责分离的人工审核不能进入精选。
- 扩展唯一 `PublicationService` 的审核事务，支持修改工程专业、生命周期、技术、场景、成熟度和成效归因；修改只能选择当前版本 accepted claim 和已有独立证据，随后由服务端重算相关性。
- 复用 `AppShell`、`IntelligenceFeedPage`、`TimelineFeed`、`IntelligenceCard`、`FeedPage`、`ItemSummary` 和证据抽屉完成 `/digital`、筛选、全部/精选、卡片、详情和审核页；不创建数字化专用卡片或平行查询/发布实现。
- 明确分列“发布方声称的成效”和“独立证据支持的成效”，所有量化结果可回到证据；卡片显示政府/行业案例源或企业自述、厂商声明、成熟度、场景、部署规模、四川路桥关系及可解释相关性，不显示为可信度。
- 新增数字案例量、来源/成熟度、claimed/verified 成效和企业待审核队列指标，以及契约、规则、迁移、固定回放、PublicationService、E2E、axe 和 1440×900 新页面截图。

### Round 04 — 安全案例生命周期

- 新增 Alembic `0005_safety_case_lifecycle`，以 `safety_case_profile`、事件、事件材料候选/决定/成员、关系候选/决定/正式关系、逐字段审核、事实冲突及追加式审计表达初报、续报、正式调查、处罚、整改、更正与撤回；迁移提供实验室降级/再升级验证，生产回滚保留事实表。
- 将日期、地区、项目、主体和事故类型五维匹配接入生产候选服务；分值与维度版本化落库且只能进入人工审核，不会自动写 `event_item`，同一事故不同阶段始终保留为独立材料并建立后续关系。
- 为伤亡、损失、正式原因和责任实施逐字段证据门禁：伤亡/损失仅接受 A0/A1 一手官方证据，原因/责任还必须来自正式调查或处罚阶段；审核决定不可逆、提交人与审核人分离，未关联事件或证据不足时默认拒绝。
- 新增冲突检测与工作台；新冲突立即把普通投影降级为“待核实”，不返回候选值、Claim ID 或证据定位，历史已接受值只保留在受控审计中；更正、撤回和后续关系均记录审核人、理由与哈希链审计。
- 冲突决定同时覆盖 `KEEP_CURRENT` 与 `ACCEPT_CANDIDATE`：落选 Claim 不再进入发布门禁、后续冲突基线或普通详情，撤回材料的事实不再参与事件头部聚合，后续有效正式材料可替代较早事实而不改写历史。
- publication gate 升级到 `4.0.0`，逐字段验证所有公开安全案例元数据均来自同一材料的 accepted claim 和有效定位证据；R4/未发布材料不能影响公开事件标题、身份、状态或关系投影，运行时角色只能读取去标识的冲突安全投影。
- 复用唯一 `PublicationService`、`FeedPage`/`ItemSummary`、`AppShell`、`IntelligenceFeedPage`、`TimelineFeed` 和 `IntelligenceCard`；在同一 `/safety` 增加规定/案例筛选及 `SafetyCaseTypeSummary`，新增事件时间线、已确认事实、待核实事实、受控标签和已审核关系/更正记录，没有平行信息流或发布链路。
- 新增固定的梅大高速“5·1”塌方灾害官方初报、续报、调查报告、追责通报和整改评估样本，锁定来源、原始 URL、SHA-256、阶段与关系；端到端演示完整五阶段证据、伤亡冲突处置、调查中状态、正式结论、撤回和更正审计。
- `/metrics` 改为仅 `PLATFORM_ADMIN`/`AUDITOR` 可访问，匿名健康与就绪探针保持不变；新增事件候选、待处理冲突、调查中案例、未结整改、关系审核及 publication gate 拒绝原因指标与结构化日志。
- Web 运行镜像改为构建阶段生成 Nuxt/Nitro 产物、运行阶段只启动预构建服务，消除开发服务器冷转换导致的首次审核页超时；首次冷启动 Playwright 保持零重试、原超时和全部断言通过。

### Round 03 — PDF、OCR 与版本变化

- 修复 Round03 基线复验发现的时间线语义：初次采集以首次发现时间作为 `activity_at`，保留独立原文发布时间；仅元数据版本不推进活动时间，实质版本以同一服务端时间推进 `activity_at/updated_at`；Feed 游标解码为数据库驱动原生 `datetime/UUID`，并以真实 PostgreSQL 锁定同活动时间的稳定 keyset 分页。
- 将 `make pdf-ocr-test` 与 `make safety-regulation-test` 改为每次创建唯一临时 PostgreSQL 数据库、私有 MinIO 桶和临时最小权限登录角色；迁移和测试不再写共享业务库或重置固定角色密码，异常、碰撞与中断路径均执行所有权感知清理，默认拒绝非回环集成端点。
- 将本地 Playwright 与 CI 统一为 2 workers，消除 Compose `nuxt dev` 在 4 workers 并发 SSR 导航下偶发的根文档无响应；保留 29 个 E2E、原超时、零本地重试和全部视觉/行为断言。
- 扩展统一 `SourceAdapter`、私有文档库和 Alembic `0004_pdf_ocr_versioning`：新增原始对象安全事实、文档版本状态事件、附件树、PDF 页面/文本块/表格单元格、版本变化、关系/法规状态候选与决定、内容生命周期、确定性摘要和事务性 Outbox；失败或隔离版本不会替换既有 `READY` 当前版本。
- 新增有界 PDF 安全检查和一层 ZIP 解包，拒绝 MIME 不符、加密、JavaScript/OpenAction/Launch/自动外链、内嵌文件、路径穿越、符号链接、嵌套归档、规范化重名和预算超限；parser 与 publisher 使用独立低并发队列和数据库角色，只有唯一 `PublicationService` 可形成发布、撤回或关系/法规状态决定。
- 新增 PyMuPDF 原生文本/表格提取与本地 Tesseract `chi_sim+eng` OCR 适配器，持久化 1 起始页码、旋转归一的千分之一 point 坐标、阅读顺序、词级置信度和页面预览；文本、语义正文、元数据与原始字节分别计算 SHA-256。
- 新增确定性变化检测和重锚：重复页眉/页脚及元数据变化归为 `METADATA_ONLY`，正文、文号、实施日期、数字/效力词/否定词等硬规则变化进入 `CONTENT_UPDATE`；实质变化通过 Outbox 使旧 Claim、摘要和发布修订进入 `UPDATE_DETECTED/RE_REVIEW_PENDING`，普通投影立即降级。
- 保持 `FeedPage`/`ItemSummary` 兼容，只增量加入文档状态和版本提示；复用 `AppShell`、`IntelligenceFeedPage`、`TimelineFeed`、`IntelligenceCard`、`EvidenceDrawer`，组合 `PdfEvidenceViewer`、`VersionTimeline` 和 `DiffView`，支持页码跳转、坐标高亮、键盘焦点归还、撤回最小投影和四断点视觉回归。
- 新增版本时间线、页级预览、按页差异、候选审核和仅升级为实质变化的 `/api/v1` 契约；publication gate 升级到 `3.0.0`，现查 `READY`、安全状态、服务端哈希、当前证据、OCR 关键字段置信度、来源准入、职责分离及关系/法规状态决定。
- 新增测试专用 PDF/OCR/表格/恶意动作/错误 MIME/超大页/附件与压缩炸弹黄金样本、真实 PostgreSQL/MinIO/ClamAV/Redis/Tesseract/parser/publisher 纵向集成门禁 `make pdf-ocr-test`，以及 PDF 解析率、OCR 可用率、低置信关键字段、版本变化和 Outbox 指标。

### Round 02 — 首个安全规定 HTML 来源

- 以应急管理部 `GOV-006` 为唯一生产连接器，新增统一 `SourceAdapter`（兼容别名 `SourceConnector`）、`DocumentParser`、固定官方 HTML 回放样本、条件请求、重试、限速、持久化熔断、幂等和 SSRF 默认拒绝防护；生产连接器保持 `CANDIDATE/disabled`，测试来源必须经真实 30 样本准入服务激活。
- 新增安全规定采集、处理、字段证据、R3 审核、发布与不可变修订迁移；原始响应先进入私有文档库，文号、机关和发布日期由规则解析并绑定 `html-p-NNNN` 段落定位，法规状态默认 `UNKNOWN`。
- 新增唯一服务端 `PublicationService`，以 `publication_gate.json` v2 和服务端现查事实执行默认拒绝门禁；普通发布允许缺省评分，未评分内容禁止进入 `/selected`，候选自报授权字段无效。
- 新增专用数据库发布角色；API、Worker、管理员和模型角色仅可读取发布表，绕过服务的直接写入由 PostgreSQL 权限拒绝。R3 提交人与审核人强制职责分离，审批、发布、修订、撤回和重发均经统一服务与哈希链审计。
- 冻结 `FeedPage`、`ItemSummary`、`FeedNotice`、`TypeSummary` v1，完成服务端 R3 白名单投影以及 `/selected`、`/all`、`/safety`、最小详情和审核工作台；复用 `AppShell`、`IntelligenceFeedPage`，仅新增一套 `TimelineFeed`、`IntelligenceCard`、`EvidenceDrawer`、`FilterPanel`。
- 新增解析黄金、连接器安全、固定回放、集成、RBAC、契约、E2E 与 axe 测试；修复 BFF 丢失 Feed 查询串和客户端 Feed hydration mismatch，保证无真实评分时精选为空且浏览器永远收不到 R3 受限字段。

### Round 01 — 来源注册与原始文档库

- 新增来源、准入策略、连接器、不可变原始对象、文档版本、附件与哈希链审计日志迁移，并将 42 个种子来源以 `CANDIDATE/disabled` 导入；
- 新增服务端来源状态机、证据重算和默认拒绝门禁，数据库字段、CSV 或请求参数均不能直接形成有效 `ACTIVE`；
- 新增 HTML/PDF 人工样本上传、MIME/大小/文件名/PDF 主动内容/杀毒校验、SHA-256 内容寻址与跨文档去重，并以摘要固定官方 ClamAV 1.5.2 镜像作为 Compose 私网健康依赖；
- 新增来源准入 API 与复用 `AppShell`、`PageHeader`、`StatusBadge`、`ResponsiveDrawer` 的管理端来源和文档元数据页面；
- 新增单元、契约、权限、真实 PostgreSQL/MinIO 集成、Playwright 与 axe 测试，以及 `make source-fixture-test`。

### Round 00A — 方案1设计系统与应用壳层

- 以 `design_tokens.json` 为单一视觉权威，建立类型安全的 `@srbg/ui`、Tailwind 与 Nuxt UI 主题映射；
- 为 Nuxt 4 接入统一应用壳层、共享 `IntelligenceFeedPage`、频道导航和真实 API/Schema 工程状态与空态；页面头以可访问的 `time` 显示实际版本检查时间，并统一承载状态；
- 完成响应式侧栏/抽屉、键盘与焦点管理、reduced-motion、axe 和四断点视觉回归，并修复 UUIDv7 请求标识、SPA 导航及当前导航的路径边界匹配；
- 将运行时烟测同步到“四川路桥 / 智安情报”文字锁定稿与真实业务空态；
- 本轮未修改后端、业务 API 或数据库迁移。

### Round 00 — 工程基线

- 建立 `apps/web`、`apps/api`、`apps/worker`、`packages/contracts`、`infra` monorepo；
- 增加 FastAPI 健康、readiness、版本与 Problem Details 契约；
- 增加 Celery Worker 健康任务和可正向执行的 Alembic 基线；
- 增加采用设计令牌的演示首页、组件测试、Playwright E2E 与 axe 无障碍测试；
- 增加 PostgreSQL、Redis、MinIO、迁移、API、Worker、Web 的固定版本 Compose 栈；
- 增加 Ruff、mypy strict、pytest、ESLint、TypeScript、Vitest、契约与安全门禁；
- 增加 GitHub Actions CI、运行时冒烟、Redis 降级恢复验收；
- 将项目工具和缓存限定在 D 盘，并验证 Docker 数据位于 `D:\Dockerdata`；
- 修复 Compose v5 项目目录、宿主端口覆盖、Nuxt CSP 水合和多版本 esbuild 回退问题；
- 修复 Windows Make 子进程无法发现 D 盘 Node 的问题，并排除运行镜像中的仓库说明与测试材料；
- 浏览器门禁复用健康运行栈，避免重复强制构建受外部镜像仓库短时故障影响；
- 增加基于 Git 可交付文件清单的确定性 Trivy 扫描，避免本地 Junction、工具和缓存污染安全门禁。
