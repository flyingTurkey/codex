# Changelog

所有重要变更记录在此文件。

## [Unreleased]

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
