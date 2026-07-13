# Changelog

所有重要变更记录在此文件。

## [Unreleased]

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
