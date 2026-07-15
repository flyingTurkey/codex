# Changelog

所有重要变更记录在此文件。

## [Unreleased]

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
